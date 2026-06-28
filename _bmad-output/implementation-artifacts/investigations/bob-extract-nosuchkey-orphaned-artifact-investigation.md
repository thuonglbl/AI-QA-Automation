# Investigation: Bob "Fetching children" crashes with S3 NoSuchKey (orphaned artifact blob)

## Hand-off Brief

1. **What happened.** While Bob extracts Confluence descendants (step 2 / "Fetching children of … via MCP"), the run
   aborts with `An unexpected error occurred: An error occurred (NoSuchKey) when calling the GetObject operation: The
   specified key does not exist.` — an S3/SeaweedFS read of an artifact blob whose object is missing.
2. **Where the case stands.** Root-cause mechanism is **Confirmed**: Bob's resume/change-detection step eagerly reads
   every saved `requirements` + `configuration` artifact blob via an **unguarded** loader; one artifact DB row whose
   storage object is absent throws `NoSuchKey`, which propagates uncaught to the WebSocket handler and kills the whole
   extraction. *Why* a blob is missing for project "PT Tool" is Hypothesized (DB rows present without their blobs —
   most likely a SeaweedFS volume reset or a DB import/transfer that didn't carry the objects).
3. **What's needed next.** Make the artifact loaders resilient — skip+log an artifact whose blob is missing instead of
   aborting (`bmad-quick-dev`). Separately confirm the orphan source with one DB-vs-bucket reconciliation query.

## Case Info

| Field            | Value                                                                                          |
| ---------------- | --------------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                            |
| Date opened      | 2026-06-25                                                                                     |
| Status           | Active — root cause Confirmed (defect), orphan source Hypothesized                             |
| System           | Windows 11; local dev (`localhost:5173` FE), backend S3/SeaweedFS artifact storage backend    |
| Evidence sources | UI screenshot (error + Bob trace), source code, git history                                    |

## Problem Statement

User report (verbatim): "lỗi rồi" + screenshot. In the "Bob — Requirements" step for project **PT Tool**, after the
trace line `Fetching children of 'https://confluence.svc.corp.ch/spaces/CORPHRSOL/pages/777945456/General+knowledge'
via MCP: processing` (10:21:10), a `system` error appears at 10:21:15:

> An unexpected error occurred: An error occurred (NoSuchKey) when calling the GetObject operation: The specified key
> does not exist.

Sidebar shows Requirements / Test Cases / Scripts / Reports all at 0 ("Empty") for PT Tool.

## Evidence Inventory

| Source                          | Status    | Notes                                                                                  |
| ------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| UI screenshot                   | Available | Exact error string + Bob trace + timestamps (10:21:10 → 10:21:15)                      |
| Backend source code             | Available | Full call chain traced end-to-end (see Source Code Trace)                              |
| Git history                     | Available | Resume/change-detection code is committed (clean `git status` on the relevant files)   |
| Backend runtime logs            | Missing   | `logger.error(... exc_info=True)` at websocket.py:379 would carry the full traceback   |
| DB artifact rows for PT Tool    | Missing   | Need `storage_path` of `requirements`/`configuration` rows to confirm which blob is gone |
| SeaweedFS bucket contents       | Missing   | Confirm the referenced key is genuinely absent (vs. an auth/bucket-name mismatch)      |

## Investigation Backlog

| # | Path to Explore                                                                 | Priority | Status | Notes                                                                 |
| - | ------------------------------------------------------------------------------- | -------- | ------ | -------------------------------------------------------------------- |
| 1 | DB: list `artifacts` (kind in requirements/configuration) for PT Tool + paths   | High     | Open   | Confirms the orphaned row(s); pinpoints which kind/blob is missing    |
| 2 | SeaweedFS: check `get_object` for those `storage_path`s exists in the bucket     | High     | Open   | Confirms NoSuchKey vs. bucket/credential/endpoint misconfig          |
| 3 | How the orphan arose (volume reset? DB import? `transfer_models_local_to_uat`?)  | Medium   | Open   | Explains "why now"; informs whether a data-repair step is also needed |
| 4 | Apply same resilience to all `_load_text_artifacts` callers (test cases, scripts)| Medium   | Open   | The defect is generic to every blob-reading loader                    |

## Timeline of Events

| Time     | Event                                                                            | Source              | Confidence |
| -------- | -------------------------------------------------------------------------------- | ------------------- | ---------- |
| 10:05:03 | Bob connect OK; "Read Confluence page via MCP: request_review"                    | screenshot          | Confirmed  |
| 10:09:59 | User submits Confluence URL (General+knowledge, page 777945456)                   | screenshot          | Confirmed  |
| 10:21:10 | "Fetching children of '…General+knowledge' via MCP: processing"                   | screenshot / bob.py:1060 | Confirmed |
| 10:21:15 | system error: NoSuchKey GetObject — extraction aborts                             | screenshot / websocket.py:383 | Confirmed |

## Confirmed Findings

### Finding 1: The error string is the WebSocket catch-all wrapper

**Evidence:** `src/ai_qa/api/websocket.py:383` — `content=f"An unexpected error occurred: {str(e)}"`, inside the
`except Exception as e:` at line 378 that logs (`exc_info=True`) and broadcasts a `system`/`error` message without
re-raising. Matches the screenshot prefix exactly.

### Finding 2: The `NoSuchKey` originates from the S3 artifact-read path

**Evidence:** `src/ai_qa/artifacts/storage.py:237` — `response = self.s3.get_object(Bucket=self.bucket_name,
Key=storage_path)` in `S3ArtifactStorage.read()`. `boto3` raises `ClientError` "An error occurred (NoSuchKey) when
calling the GetObject operation: The specified key does not exist." verbatim when the key is absent. (The active
backend is S3/SeaweedFS — the local backend `LocalArtifactStorage.read()` at storage.py:138 would instead raise
`FileNotFoundError`.)

### Finding 3: Bob's extraction step eagerly reads ALL saved artifact blobs (resume/change-detection)

**Evidence:** `src/ai_qa/agents/bob.py:1153` — `for art in adapter.load_requirement_markdown():` and bob.py:1170 —
`all_meta = adapter.load_all_metadata()`, both inside `_extract_descendants` (runs right after the "Fetching children"
trace at bob.py:1060). This block is the committed resume / version-gated reuse feature (clean `git status`; landed
with recent work, cf. memory `bob-resume-continue-extraction`).

### Finding 4: The loader has NO guard around the blob read — one missing object aborts the whole load

**Evidence:** chain with no try/except on the read:

- `src/ai_qa/pipelines/artifact_adapter.py:162` `load_requirement_markdown()` → `_load_text_artifacts(kind="requirements")`
- `artifact_adapter.py:535-537` `_load_text_artifacts` → `list_artifacts(...)` then `_to_pipeline_artifact(art)` per row
- `artifact_adapter.py:540` `_to_pipeline_artifact` → `content_bytes = self.service.read_current_content(artifact)` (unguarded)
- `src/ai_qa/artifacts/service.py:247` `read_current_content` → `return self.storage.read(artifact.storage_path)`
- → storage.py:237 `get_object` → `NoSuchKey`.

`load_all_metadata` (artifact_adapter.py:378) and `load_metadata` (361) share the same `_load_text_artifacts` →
`_to_pipeline_artifact` read, so a missing `configuration` blob fails identically. The `except json.JSONDecodeError,
ValueError:` they wrap only guards JSON *parsing*, not the storage read.

## Deduced Conclusions

### Deduction 1: A `requirements` (or `configuration`) artifact row for PT Tool points to a missing storage object

**Based on:** Findings 1–4.

**Reasoning:** Between the "Fetching children … processing" trace (bob.py:1060) and the crash, the only operations that
touch S3 are `load_requirement_markdown()` (bob.py:1153) and `load_all_metadata()` (bob.py:1170). The MCP calls
(`get_children_by_id`, `read_page_by_id`) cannot raise a boto3 `GetObject` error. Therefore the `NoSuchKey` is thrown
while reading a saved artifact blob whose DB row exists but whose object is absent from the bucket.

**Conclusion:** This is a data/robustness defect: the resume step assumes every artifact row has a readable blob and
crashes the entire extraction when that invariant is violated, instead of skipping the orphan.

### Deduction 2: "Why now" — the resume feature turned a previously-harmless orphan into a hard failure

**Based on:** Finding 3 + memory `bob-resume-continue-extraction`.

**Reasoning:** Before resume/change-detection, `_extract_descendants` did not read existing requirement/metadata blobs;
a pre-existing orphaned row was inert. The new code reads all of them up front, so the first orphan now aborts the run.

## Hypothesized Paths

### Hypothesis 1 (user premise): "lỗi rồi" is a generic/unknown failure

**Status:** Refuted — the failure is specific and located (S3 `NoSuchKey` on an artifact-blob read in Bob's resume step).

**Resolution:** Settled by Findings 1–4 + Deduction 1.

### Hypothesis 2: The missing blob was introduced by a DB/storage divergence (volume reset or data import)

**Status:** Confirmed (2026-06-25).

**Theory:** PT Tool has artifact DB rows from a prior run, but the matching object(s) are gone.

**Supporting indicators:** Sidebar shows 0 artifacts for PT Tool (FE hides raw/non-`.md` companions, so rows can exist
while the tree looks empty); the error is `NoSuchKey` (object missing), not auth/permission.

**Resolution:** User confirmed — "tại mình tự xóa trên fs" (he manually deleted the object(s) from storage while the
DB rows remained). This is exactly the DB-without-blob divergence; it validates the robustness fix (loaders must
tolerate a missing blob). No automated data-repair is required for this case.

## Missing Evidence

| Gap                                   | Impact                                                           | How to Obtain                                                                 |
| ------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Backend traceback for this error      | Confirms which loader/line threw (requirements vs configuration) | Read backend console/log around 10:21:15 (websocket.py:379 logs `exc_info`)  |
| PT Tool artifact rows + `storage_path`| Identifies the exact orphaned object(s)                          | `SELECT id, kind, name, storage_path FROM artifacts WHERE project_id=…`       |
| Bucket object existence               | Distinguishes true orphan vs. config/endpoint mismatch          | `aws s3api head-object` / SeaweedFS check for each `storage_path`             |

## Source Code Trace

| Element       | Detail                                                                                                          |
| ------------- | -------------------------------------------------------------------------------------------------------------- |
| Error origin  | `src/ai_qa/artifacts/storage.py:237` `S3ArtifactStorage.read` → boto3 `get_object` raises `NoSuchKey`           |
| Surfaced at   | `src/ai_qa/api/websocket.py:383` catch-all → "An unexpected error occurred: …"                                  |
| Trigger       | `src/ai_qa/agents/bob.py:1153` `load_requirement_markdown()` (and bob.py:1170 `load_all_metadata()`) in `_extract_descendants` |
| Read path     | `artifact_adapter.py:540` `_to_pipeline_artifact` → `service.py:247` `read_current_content` → `storage.read` (no try/except) |
| Condition     | An `artifacts` DB row exists whose `storage_path` object is absent from the bucket (orphaned blob)              |
| Related files | `artifact_adapter.py` (all `_load_text_artifacts` callers: requirements, testcase, raw_html, configuration); `service.py`; `storage.py` (both backends) |

## Conclusion

**Confidence:** High (defect mechanism) / Medium (orphan source).

Confirmed: Bob's resume/change-detection step (`_extract_descendants`) eagerly reads every saved `requirements` and
`configuration` artifact blob through an **unguarded** loader (`_to_pipeline_artifact` → `read_current_content` →
`storage.read`). For project PT Tool, at least one such DB row references a storage object that no longer exists, so
`get_object` raises `NoSuchKey`; the exception is uncaught until the WebSocket catch-all (websocket.py:378), which
aborts the entire extraction and shows the generic banner. The defect is that a single orphaned blob takes down the
whole load instead of being skipped. Hypothesized (data gap): the orphan stems from DB rows present without their
SeaweedFS objects (volume reset or a data import/transfer) — to be confirmed with a DB-vs-bucket reconciliation.

## Recommended Next Steps

### Fix direction

Make artifact loading resilient to a missing blob, at the narrowest correct layer:

- In `_to_pipeline_artifact` / `_load_text_artifacts` (artifact_adapter.py:535-552), wrap the `read_current_content`
  call and on a storage "not found" error (`botocore.exceptions.ClientError` with code `NoSuchKey` for S3,
  `FileNotFoundError` for local) **log a warning and skip** that artifact rather than propagating. This unblocks Bob
  immediately and fixes every loader (requirements, configuration, test cases, raw_html) at once.
- Consider a small `StorageObjectNotFound` exception raised by both `*.read()` backends so callers can catch one type
  (avoids leaking boto3 specifics into the adapter).
- Optional hardening: have the WebSocket handler surface a friendlier message for storage-missing errors.

### Diagnostic

- Read the backend log line at websocket.py:379 (logged with `exc_info=True`) to confirm the exact failing loader/line.
- Run Backlog #1 + #2 (DB rows + bucket check) to confirm the orphaned object and decide whether a one-off data repair
  (re-extract or prune the dangling rows) is also warranted.

## Reproduction Plan

1. In a project with the S3/SeaweedFS backend, create a `requirements` (or `configuration`) artifact via Bob.
2. Delete the underlying object from the bucket (leave the DB row), e.g. `aws s3api delete-object --key <storage_path>`.
3. Re-enter Bob and run descendant extraction ("Fetching children") → expect the `NoSuchKey` banner today; after the
   fix, expect the orphan to be skipped (with a logged warning) and extraction to proceed.

## Side Findings

- `except json.JSONDecodeError, ValueError:` at artifact_adapter.py:365 and :381 is valid PEP 758 syntax on Python
  3.14 — not a bug (noted because subagents frequently false-flag it; cf. memory).
- The same unguarded-read defect applies to `load_test_cases` / `load_approved_test_cases` / `load_raw_html`
  (artifact_adapter.py:216, 226, 397) — any orphaned blob in those kinds would crash Mary/Sarah equivalently.
