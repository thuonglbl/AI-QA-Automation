---
title: 'Resilient artifact loading when a storage blob is missing'
type: 'bugfix'
created: '2026-06-25'
status: 'done'
baseline_commit: '2c8e0d79dee0b35dcfac9f1e322e04997ad2bdeb'
context:
  - '{project-root}/project-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/investigations/bob-extract-nosuchkey-orphaned-artifact-investigation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When an artifact DB row exists but its underlying storage object is gone (e.g. the
user deleted it on the filesystem), reading it throws — S3/SeaweedFS raises botocore `NoSuchKey`,
local raises `FileNotFoundError`. Bob's resume/change-detection step bulk-reads every saved
`requirements` + `configuration` blob, so a single orphan crashes the whole extraction with
"An unexpected error occurred: … NoSuchKey …" (confirmed in the investigation case file). Every
pipeline loader (Mary test cases, Sarah scripts) shares the same unguarded read.

**Approach:** Introduce one storage-agnostic exception `StorageObjectNotFound(FileNotFoundError)`
raised by both backends' `read()` when the object is absent. The pipeline loaders skip+log an
artifact whose blob is missing instead of aborting the batch. Subclassing `FileNotFoundError`
keeps the existing `except FileNotFoundError` handlers working (and finally maps an S3 missing-blob
download to 404 too — a latent bug today, since that handler only caught the local error).

## Boundaries & Constraints

**Always:** Fix at the narrowest shared layer so all loaders benefit (requirements, configuration,
testcase, playwright_script, raw_html). Only a genuinely-missing object is swallowed — every other
error (ValueError path-traversal, S3 AccessDenied/NoSuchBucket, network/OSError) must propagate
unchanged. Each skip logs a WARNING with artifact id, kind, name, and storage_path. Follow
project-context.md (uv, Ruff, mypy-strict on `src`, pytest; code clean under Pyrefly too).

**Ask First:** If making `StorageObjectNotFound` subclass `FileNotFoundError` turns out to change
behavior for any caller beyond artifacts.py download + the pipeline loaders.

**Never:** Do not change the API download endpoint to *skip* a missing artifact — a direct download
of a missing blob must still surface 404 (the subclass handles this automatically). Do not delete
or auto-repair orphaned DB rows. Do not catch broad `Exception` in the loaders. No new dependency.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Blob present | artifact row + object exists | bytes returned; artifact included in load | N/A |
| S3 object deleted | row exists, `get_object` → `ClientError` code `NoSuchKey`/`404` | `read()` raises `StorageObjectNotFound` | re-raise as typed exc |
| Local file deleted | row exists, file missing | `read()` raises `StorageObjectNotFound` | wrap `FileNotFoundError` |
| One orphan in a batch | N requirement rows, 1 blob missing | loader returns N-1, logs WARNING for the orphan | skip the orphan |
| Other S3 error | `ClientError` code `AccessDenied`/`NoSuchBucket` | propagates unchanged | not swallowed |
| Invalid/traversal path | local `_resolve_storage_path` → `ValueError` | propagates unchanged | not swallowed |
| `load_raw_html` orphan | raw_html row, blob missing | returns `None` (+ WARNING) | skip |
| Download missing blob | GET `/{id}/content`, blob gone (either backend) | HTTP 404 | via `except FileNotFoundError` |

</frozen-after-approval>

## Code Map

- `src/ai_qa/artifacts/storage.py` -- define `StorageObjectNotFound(FileNotFoundError)`; both `read()` methods map their native missing-object error to it; document it on the `ArtifactStorage` Protocol `read`.
- `src/ai_qa/pipelines/artifact_adapter.py` -- `_load_text_artifacts` (line ~535) skip+log per-artifact on `StorageObjectNotFound`; `load_raw_html` (line ~397) returns `None` on it. Covers requirements/testcase/playwright_script/configuration loaders + Bob resume path (`bob.py:1153`,`:1170`).
- `src/ai_qa/api/artifacts.py` -- download endpoint (line ~367): no code change needed (subclass is caught by existing `except FileNotFoundError`); verify with a test.
- `src/ai_qa/artifacts/service.py` -- `read_current_content` (line 247): no change; propagates the typed exception.
- `tests/unit/test_artifact_service.py` -- storage-backend tests (both backends + ClientError mock).
- `tests/pipelines/test_pipeline_artifact_adapter.py` -- loader skip + `load_raw_html` tests.
- `tests/api/test_artifact_api.py` -- 404 on missing-blob download.

## Tasks & Acceptance

**Execution:**
- [x] `src/ai_qa/artifacts/storage.py` -- add `class StorageObjectNotFound(FileNotFoundError)` with a clear message (include storage_path); `LocalArtifactStorage.read` wraps `read_bytes()`'s `FileNotFoundError`; `S3ArtifactStorage.read` catches botocore `ClientError`, re-raises as `StorageObjectNotFound` only for codes `{"NoSuchKey","404"}`, re-raises all other `ClientError` unchanged; add the raised-exception note to the Protocol `read` docstring. Hoist `cast` to the top-level typing import.
- [x] `src/ai_qa/pipelines/artifact_adapter.py` -- rewrite `_load_text_artifacts` as a loop that calls `_to_pipeline_artifact` inside `try/except StorageObjectNotFound`, logging a WARNING (id/kind/name/storage_path) and skipping; wrap `load_raw_html`'s `read_current_content` in `try/except StorageObjectNotFound` → log WARNING + `return None`. Import `StorageObjectNotFound`.
- [x] `tests/unit/test_artifact_service.py` -- assert `StorageObjectNotFound` is a `FileNotFoundError`; local `read` of a deleted file raises it; S3 `read` raises it on a mocked `NoSuchKey` `ClientError` and re-raises on `AccessDenied`.
- [x] `tests/pipelines/test_pipeline_artifact_adapter.py` -- save two requirements via the adapter, delete one underlying file, assert `load_requirement_markdown()` returns only the survivor (+ a warning is emitted); assert `load_raw_html` returns `None` when its blob is deleted.
- [x] `tests/api/test_artifact_api.py` -- GET `/{id}/content` returns 404 when the artifact's blob is missing.

**Acceptance Criteria:**
- Given an orphaned artifact row among valid ones, when any pipeline loader runs, then the valid artifacts load and Bob's "Fetching children" extraction proceeds (no "unexpected error" banner).
- Given a missing blob, when read via either backend, then `StorageObjectNotFound` is raised; given a non-missing storage error, then it propagates unchanged.
- Given `uv run mypy src` and `uv run ruff check src/ tests/` and the full `uv run pytest`, when run, then all pass.

## Spec Change Log

- 2026-06-25 (implementation): Renamed the new exception `StorageObjectNotFound` → `StorageObjectNotFoundError` to satisfy Ruff `N818` (exception names must end in `Error`) and match the codebase convention. Identifier-only change; the frozen Intent text still reads `StorageObjectNotFound` but the implemented class is `StorageObjectNotFoundError(FileNotFoundError)`. Behavior unchanged.

## Verification

**Commands:**
- `uv run ruff check --fix src/ tests/ && uv run ruff format src/ tests/` -- expected: clean
- `uv run mypy src` -- expected: no errors
- `uv run pytest tests/unit/test_artifact_service.py tests/pipelines/test_pipeline_artifact_adapter.py tests/api/test_artifact_api.py` -- expected: pass (use `--no-cov` for subset)
- `uv run pytest` -- expected: full suite green (coverage gate satisfied)

**Manual checks:**
- In a project with an artifact whose blob was deleted on the FS, re-enter Bob → "Fetching children" completes instead of showing the NoSuchKey banner.

## Suggested Review Order

**Storage layer — the new typed exception**

- Entry point: design intent — subclass `FileNotFoundError` so existing 404 handlers cover BOTH backends.
  [`storage.py:12`](../../src/ai_qa/artifacts/storage.py#L12)

- S3 backend maps botocore `NoSuchKey`/`404` → typed exception; every other `ClientError` propagates.
  [`storage.py:250`](../../src/ai_qa/artifacts/storage.py#L250)

- Local backend wraps `FileNotFoundError` (path-traversal `ValueError` still propagates).
  [`storage.py:150`](../../src/ai_qa/artifacts/storage.py#L150)

**Loader resilience — the actual fix**

- Shared loader skips+logs an artifact whose blob is missing — covers every kind + Bob's resume path.
  [`artifact_adapter.py:546`](../../src/ai_qa/pipelines/artifact_adapter.py#L546)

- `load_raw_html` returns `None` on a missing blob instead of raising.
  [`artifact_adapter.py:398`](../../src/ai_qa/pipelines/artifact_adapter.py#L398)

**API behavior preserved**

- Download endpoint still 404s a missing blob — now for S3 too (subclass caught by existing handler).
  [`artifacts.py:369`](../../src/ai_qa/api/artifacts.py#L369)

**Tests**

- Backend: subclass relationship + both backends + `NoSuchKey`/`404`/non-missing `ClientError` branches.
  [`test_artifact_service.py:933`](../../tests/unit/test_artifact_service.py#L933)

- Loader skip + `load_raw_html` None + `load_all_metadata` skip (the Bob-resume path).
  [`test_pipeline_artifact_adapter.py:1128`](../../tests/pipelines/test_pipeline_artifact_adapter.py#L1128)

- API GET `/content` → 404 when the blob is missing.
  [`test_artifact_api.py:257`](../../tests/api/test_artifact_api.py#L257)
