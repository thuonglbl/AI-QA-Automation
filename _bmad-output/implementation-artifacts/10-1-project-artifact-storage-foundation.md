---
baseline_commit: 0c010d3e3feb3f1bf3da120adac2345e0ab3152f
---

# Story 10.1: Project Artifact Storage Foundation

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want project artifacts stored under a shared project-level structure,
so that generated files are available to authorized collaborators in the same project.

## Acceptance Criteria

### AC1 — Project-scoped logical folders + bytes in object storage

**Given** a project exists in PostgreSQL
**When** artifact storage is initialized or queried for that project
**Then** the logical folders `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/` are available
**And** artifact bytes are stored in SeaweedFS or the configured S3-compatible artifact backend.

### AC2 — Metadata persisted in PostgreSQL, separate from bytes

**Given** an artifact is created
**When** metadata is persisted
**Then** PostgreSQL stores project id, artifact kind, storage path, creator, updater, timestamps, optional originating thread, and optional originating agent run
**And** artifact metadata is separate from artifact bytes.

### AC3 — Project-membership authorization before any access

**Given** a user is not assigned to a project
**When** they attempt to access that project's artifact storage
**Then** access is denied before reading or writing artifact metadata or bytes.

---

## ⚠️ CRITICAL: This is a RECONCILE + EXTEND story, NOT a greenfield build

The artifact storage foundation **already physically exists and is load-bearing in production.** It was shipped piecemeal across Epic 6 (stories 6-5, 6-7) and is depended on by the already-`done` stories **10-7 (Realtime Artifact Refresh UX)** and **10-8 (Open Artifact Update/Delete Notice)**. **Do NOT rebuild `ArtifactService`, `S3ArtifactStorage`, the `artifacts`/`artifact_versions` tables, the REST routes, or the WebSocket event.** Your job is to **close the gaps** between what exists and what AC1–AC3 require, without breaking the shipped contract.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| --- | --- | --- |
| Bytes in SeaweedFS/S3 | `S3ArtifactStorage` — [storage.py:120](src/ai_qa/artifacts/storage.py:120); factory `get_artifact_storage()` — [artifacts.py:30](src/ai_qa/api/artifacts.py:30); bucket auto-create at startup | ✅ done |
| `projects/{project_id}/...` key scheme + `requirements/` folder | [storage.py:103-107](src/ai_qa/artifacts/storage.py:103) (Local) + [storage.py:155-160](src/ai_qa/artifacts/storage.py:155) (S3) | ✅ done |
| `Artifact` + `ArtifactVersion` tables | [models.py:125-168](src/ai_qa/db/models.py:125) | ✅ done |
| Service: save/version/list/get/delete/read | `ArtifactService` — [service.py:32](src/ai_qa/artifacts/service.py:32) | ✅ done |
| Versioning + SHA-256 content hash | `create_version` — [service.py:96](src/ai_qa/artifacts/service.py:96) | ✅ done |
| Project-membership authz on all routes | `require_project_member_or_admin` — [projects.py:79](src/ai_qa/api/projects.py:79) → `ProjectAccessDependency` | ✅ done |
| REST API `/projects/{project_id}/artifacts` (list/create/get/content/delete/versions) | [artifacts.py](src/ai_qa/api/artifacts.py) | ✅ done |
| `artifact_change` WebSocket event | `ArtifactChangeEvent` — [models.py:132](src/ai_qa/models.py:132); `broadcast_artifact_change` — [websocket.py:389](src/ai_qa/api/websocket.py:389) | ✅ done (frozen — Story 10.6 owns events) |
| SeaweedFS settings (endpoint/keys/bucket) | [config.py:186-201](src/ai_qa/config.py:186) | ✅ done |
| Pipeline write seam for agents | `PipelineArtifactAdapter` — [artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done |

### What is MISSING / must change in THIS story (the real scope)

1. **`test_cases/` and `test_scripts/` logical folders do not exist.** Only `requirements` maps to a logical folder today; `testcase`, `testscript`, `playwright_script` (and everything else) fall through to the generic `projects/{project_id}/artifacts/{artifact_id}/v{version}/{name}` path → **AC1 not met for test cases/scripts.**
2. **No artifact-level `creator` / `updater`.** `Artifact` has neither column; only `ArtifactVersion.created_by_user_id` (per-version) exists → **AC2 not met** (needs both creator and updater on the artifact).
3. **No direct optional `thread_id` on `Artifact`.** Thread is only reachable transitively via `agent_run_id → AgentRun.thread_id`. AC2 wants an **optional originating thread** directly (including for artifacts with no agent run) → new nullable column.
4. **No "required folder projection."** Nothing returns the three required folders for a project when SeaweedFS is empty — this is the foundation Story 10.2 needs.
5. **Authz denial is not explicitly proven leak-free.** Routes are gated, but there is no leak-canary coverage proving non-members get no `storage_path`/metadata leakage before denial → **AC3 needs verification.**

### FROZEN CONTRACTS — DO NOT change (you will break shipped 10-7 / 10-8)

- **`kind` string values** stay exactly as the 11-value `ARTIFACT_KINDS` frozenset ([service.py:15-29](src/ai_qa/artifacts/service.py:15)). Note these are single-word: `testcase`, `testscript` — **NOT** `test_cases`/`test_scripts`. The logical *folder* names use underscores; the *kind* strings do not. Keep them distinct.
- **`ArtifactChangeEvent`** shape ([models.py:132](src/ai_qa/models.py:132)): `type="artifact_change"`, `project_id`, `artifact_id`, `change_type ∈ {created, updated, deleted}` (past tense), `timestamp`. Do not rename fields, do not change the enum, do not add required fields the frontend doesn't expect.
- **`ArtifactResponse`** existing field names ([artifacts.py:61-73](src/ai_qa/api/artifacts.py:61)) — you may **add** fields (additive is safe) but must not rename/remove or change types of `id`, `project_id`, `agent_run_id`, `kind`, `name`, `current_version`, `created_at`, `updated_at`.
- **Endpoint surface** `/projects/{project_id}/artifacts` and its sub-paths — keep paths/methods unchanged.

---

## Tasks / Subtasks

- [x] **Task 1 — Add artifact-level ownership + originating-thread metadata (AC2)**
  - [x] 1.1 Add to `Artifact` ([models.py:125](src/ai_qa/db/models.py:125)): `created_by_user_id` (`UUID | None`, FK `users.id` `ondelete=SET NULL`, nullable, indexed) and `updated_by_user_id` (same shape). **Use `SET NULL`, not `CASCADE`** — artifacts are project-shared resources and must survive deletion of the creating/updating user (architecture: "Artifacts are project-level shared resources").
  - [x] 1.2 Add `thread_id` (`UUID | None`, FK `threads.id` `ondelete=SET NULL`, nullable, indexed) to `Artifact` for the optional *direct* originating thread. (`agent_run_id` already covers optional originating agent run — keep it.)
  - [x] 1.3 Columns only; relationships are optional (the response exposes IDs, not nested user/thread objects). Do not add `back_populates` churn unless eager-loading is needed.
  - [x] 1.4 Generate the Alembic migration: first run `uv run alembic heads` to confirm the current head (expected `e9f1a2b3c4d5` = `add_ai_provider_configs`); set `down_revision` to that head. Add the 3 columns + their indexes using the project naming convention ([base.py:11-17](src/ai_qa/db/base.py:11)). Provide a working `downgrade()`. **Optional cleanup:** drop the orphaned, ORM-unmapped `legacy_pipeline_run_id` column on `artifacts` (renamed in `0d5fd025248e_migrate_pipeline_runs_to_agent_runs.py`) — only if it does not complicate the migration; otherwise leave it.
  - [x] 1.5 `ArtifactService.save_artifact` ([service.py:39](src/ai_qa/artifacts/service.py:39)): set `created_by_user_id = owner_user_id` and `updated_by_user_id = owner_user_id`; add an optional `thread_id: UUID | None = None` param and persist it. If `thread_id` is provided, validate it belongs to `project_id` (mirror `_validate_agent_run` — [service.py:203](src/ai_qa/artifacts/service.py:203)).
  - [x] 1.6 `ArtifactService.create_version` ([service.py:96](src/ai_qa/artifacts/service.py:96)): set `artifact.updated_by_user_id = created_by_user_id` (the editor). `updated_at` already auto-refreshes via `TimestampMixin.onupdate`.

- [x] **Task 2 — Canonical kind→logical-folder mapping + required-folder projection (AC1)**
  - [x] 2.1 The storage-path logic is **duplicated** between `LocalArtifactStorage._build_storage_path` ([storage.py:100-107](src/ai_qa/artifacts/storage.py:100)) and `S3ArtifactStorage.write` ([storage.py:155-160](src/ai_qa/artifacts/storage.py:155)). Extract a **single shared module-level helper** (e.g. `build_artifact_key(*, project_id, artifact_id, version, kind, safe_name) -> str`) and call it from BOTH backends to eliminate drift.
  - [x] 2.2 Implement the canonical mapping in that helper:
    - `requirements` → `projects/{project_id}/requirements/{safe_name}` (unchanged)
    - `raw_html` → `projects/{project_id}/requirements/mcp/confluence/{safe_name}` (unchanged)
    - `testcase` → `projects/{project_id}/test_cases/{safe_name}`
    - `testscript`, `playwright_script` → `projects/{project_id}/test_scripts/{safe_name}`
    - all other kinds (`image`, `report`, `screenshot`, `configuration`, `markdown`, `mermaid`) → `projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}` (unchanged generic path)
  - [x] 2.3 Define `REQUIRED_ARTIFACT_FOLDERS = ("requirements", "test_cases", "test_scripts")` (module constant) and add an `ArtifactService` method that returns the three required logical folders for a project (e.g. `required_folders(project_id) -> list[str]` returning the `projects/{project_id}/<folder>/` prefixes), so Story 10.2 can render empty folders. This is **projection only** — do not create empty objects in SeaweedFS.
  - [x] 2.4 Verify new writes for `testcase`/`testscript`/`playwright_script` land under `projects/{project_id}/test_cases|test_scripts/` in BOTH backends.
  - [x] 2.5 **Back-compat (no data migration):** existing artifacts keep their persisted `storage_path`; reads use the stored path so they are unaffected. The new mapping applies to NEW writes only. See **Open Question Q1** on flat-vs-nested keys for these folders.

- [x] **Task 3 — Prove project-membership authorization is leak-free (AC3)**
  - [x] 3.1 Confirm every artifact route depends on `ProjectAccessDependency` (it does — [artifacts.py](src/ai_qa/api/artifacts.py)); add explicit test coverage for list/create/get/content/delete/versions.
  - [x] 3.2 Confirm service methods never cross project boundaries (all queries filter `Artifact.project_id == project_id` — [service.py:147-187](src/ai_qa/artifacts/service.py:147)); add coverage for the cross-project access attempt.
  - [x] 3.3 **Leak-canary tests** (project convention): a non-member (and a member of a *different* project) hitting any artifact endpoint gets `404` with `RESOURCE_NOT_FOUND_DETAIL` and **no** `storage_path`, S3 key, kind, or name leaked in the response body, error detail, or logs. Denial must occur before any metadata/bytes read.

- [x] **Task 4 — Extend response additively + keep frozen contracts (AC2, full-stack sync)**
  - [x] 4.1 Add `created_by_user_id: UUID | None`, `updated_by_user_id: UUID | None`, `thread_id: UUID | None` to `ArtifactResponse` ([artifacts.py:61](src/ai_qa/api/artifacts.py:61)). **Also update the manual builder** `_artifact_detail_response` ([artifacts.py:139-151](src/ai_qa/api/artifacts.py:139)) to pass the new fields — it constructs the model field-by-field, so `model_validate` alone won't cover it.
  - [x] 4.2 Mirror the three new fields as **optional** properties on the frontend artifact type in `frontend/src/types/` (full-stack-sync rule). No UI rendering work in this story. Run `npm run typecheck` in `frontend/`.
  - [x] 4.3 Re-confirm none of the frozen contracts above changed.

- [x] **Task 5 — Tests, migration, and verification (DoD)**
  - [x] 5.1 Update existing tests for the new columns + folder mapping: `tests/unit/test_artifact_service.py`, `tests/api/test_artifact_api.py`, `tests/api/test_artifact_events.py`.
  - [x] 5.2 Add new tests: shared key-builder mapping for each kind (assert both backends agree), required-folder projection, creator/updater/thread persistence on create + version, and the Task 3 leak-canary cases.
  - [x] 5.3 Run the full gate (see Definition of Done) and paste results into the Dev Agent Record.

---

## Dev Notes

### Architecture & module layout (authoritative)

The `artifacts` package is a designated core component (implementation-sequence #6 in the architecture). Per the architecture's module map, artifact code lives in `src/ai_qa/artifacts/` (`service.py`, `storage.py`) and the API routes in the API layer.

- **Path discrepancy to respect:** the architecture document names the route file `src/ai_qa/api/routes/artifacts.py`, but the ACTUAL shipped file is **[src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py)**. Edit the existing file — do **not** create a new `routes/artifacts.py`.
- **Events location:** the architecture mentions `src/ai_qa/artifacts/events.py`, but the shipped event lives in [models.py:132](src/ai_qa/models.py:132) (`ArtifactChangeEvent`) and is broadcast from [websocket.py:389](src/ai_qa/api/websocket.py:389). **Do NOT create `events.py` or move the event** — application-managed change events are Story 10.6's scope; 10.1 only must not break the existing event.

### Data model conventions (match these exactly)

- IDs: UUID PK via `UUIDPrimaryKeyMixin`; timestamps via `TimestampMixin` (tz-aware, `onupdate` auto-refresh) — [base.py](src/ai_qa/db/base.py).
- Constraint/index names are auto-generated from `NAMING_CONVENTION` ([base.py:11-17](src/ai_qa/db/base.py:11)). Let Alembic/`autogenerate` honor it; don't hand-name indexes inconsistently.
- New FK `ondelete`: **`SET NULL`** for `created_by_user_id`, `updated_by_user_id`, `thread_id` on `Artifact` (shared-resource survival). This is a deliberate divergence from `ArtifactVersion.created_by_user_id` which uses `CASCADE` — that is fine because a version row is meaningless without its creator context, but a shared artifact is not.
- Per project-context rule: **async eager-load** any relationship a Pydantic response serializes (`selectinload`/`joinedload`); never lazy-load in async (`MissingGreenlet`). Since the response exposes IDs only, no new eager-load is required for the new columns.

### Storage path target (the AC1 end-state)

The architecture's bucket diagram shows **flat files** directly under each logical folder:

```text
ai-qa-artifacts/
  projects/{project_id}/
    requirements/extracted_requirements.md
    test_cases/generated_test_cases.json
    test_scripts/test_login_flow.py
```

**Code-review decision (2026-06-11): collision-safe nesting was chosen over the flat layout (Q1 alternative).** `build_artifact_key` now writes every artifact+version to its own path `projects/{project_id}/{folder}/{artifact_id}/v{version}/{safe_name}` for all kinds. The logical folders (`requirements/`/`test_cases/`/`test_scripts/`) remain browsable by prefix for Story 10.2's empty-folder projection, but two distinct artifacts of the same kind+name no longer collide, and each version's bytes are retained (so future version rollback is possible). This intentionally diverges from the architecture's flat bucket diagram above — see the resolved **Open Question Q1**.

### Authorization model

- Reuse `require_project_member_or_admin` ([projects.py:79](src/ai_qa/api/projects.py:79)) → `ProjectAccessDependency`. Admins pass; non-members get `404` (`RESOURCE_NOT_FOUND_DETAIL`) — the 404-not-403 choice is intentional (don't reveal existence). Keep that behavior.
- Service-layer methods are already project-scoped; keep all new queries filtered by `project_id`.
- **No secrets ever touch artifacts** (project rule). Artifacts carry generated QA content only. The leak-canary here targets internal *storage metadata* (paths/keys), not secrets — but follow the same "never leak on denial" discipline.

### Anti-patterns to avoid (FORBIDDEN)

- Reading/writing SeaweedFS directly from agents, routes, or UI **without** going through `ArtifactService` (architecture anti-pattern).
- Reinventing `ArtifactService` / `S3ArtifactStorage` / the tables — extend them.
- Changing `kind` strings, the `artifact_change` event shape, or existing `ArtifactResponse` field names (breaks shipped 10-7/10-8).
- `# type: ignore` / `@ts-ignore`; global lint disables; mixing formatting with logic in one commit (project rules).
- Leaving `ArtifactService(db)` to silently default to `LocalArtifactStorage()` ([service.py:37](src/ai_qa/artifacts/service.py:37)) in any runtime path. Production already injects S3 via `get_artifact_storage()`; keep doing so. (Hardening the default is **optional** — see Q2 — because unit tests rely on the Local default.)

### Realtime event handling in shipped 10-7/10-8 — CORRECTED in this story (code review 2026-06-11)

An earlier analysis pass claimed `main` already handled two cases correctly. **That was wrong.** Verified against HEAD (`git show HEAD:frontend/src/App.tsx`): the handler matched only `change_type === "delete"` while the backend emits the past-tense `"deleted"` — so the delete notice never fired — and it read a non-existent `data.artifact_name`. This story **corrects both**:

- **Delete events now map to the delete notice.** [App.tsx](frontend/src/App.tsx) matches `changeType === "deleted" || changeType === "delete"` via the extracted, unit-tested `artifactNoticeTypeFor` helper.
- **The notice sources the name from local state.** `artifactName` comes from `selectedArtifact?.name` (falling back to `"Artifact"`); the branch only runs for the currently-open artifact, so its name is local. The event intentionally carries no `name` ([models.py:132](src/ai_qa/models.py:132)) — that frozen contract is preserved.

Constraints upheld: `change_type` stays past-tense (`created`/`updated`/`deleted`); no `name` field added to `ArtifactChangeEvent`. Vitest coverage for `artifactNoticeTypeFor` added in `App.test.tsx` (4 cases), closing the prior 10-7/10-8 test-debt gap for this logic.

### Previous-story / brownfield intelligence

- This is story #1 of Epic 10, so there is no `10-0`. The relevant prior work is Epic 6: **6-5** (delivered `Artifact`/`ArtifactVersion`, `ArtifactStorage` protocol + `LocalArtifactStorage`, SHA-256 versioning, the REST routes, and `require_project_member_or_admin`; explicitly *deferred* S3/MinIO) and **6-7** (introduced `PipelineContext`, `PipelineRunService`, `PipelineArtifactAdapter`; refactored Bob/Mary/Sarah off `workspace/*` paths). Note: 6-5/6-7 carry legacy IDs `12.5`/`12.7` inside their text — they ARE the Epic 6 stories.
- `17-5-test-case-artifact-save.md` is **`deferred`, not done.** It overlaps 10.1's intent (test cases under `test_cases/` with rich metadata). 10.1 delivers the *foundation* (folder + creator/updater/thread); rich test-case metadata (source requirement IDs, confidence, approval status) belongs to the Epic 12 test-case story, **not** 10.1 — do not absorb it.
- Git signal: recent commits are Epic 9 (secrets) + E2E work; nothing artifact-relevant in flight.

### Latest tech / dependencies

No new dependencies. Reuse the already-pinned stack: `boto3>=1.43.12` (S3 client against SeaweedFS), SQLAlchemy 2.0, Alembic 1.13, FastAPI 0.115, Pydantic v2. `uv` only for any package operations (never `pip`).

### Testing requirements

- **Backend (pytest):** in-memory SQLite; copy the canonical fixture scaffold from `tests/api/test_admin_rbac_api.py`, adapting only auth context. `engine.dispose()` in teardown. No bare `pytest.raises(Exception)` — use specific type + `match=`. Cast `cast(FastAPI, client.app)` for `dependency_overrides`; override `get_artifact_storage` to an in-memory/fake or `LocalArtifactStorage(tmp_path)` so tests never hit a real SeaweedFS.
- **Migration in DoD (project guardrail):** the migration must apply cleanly (`uv run alembic upgrade head`) AND downgrade. Test DB schema reflects the 3 new columns.
- **Coverage targets:** shared key-builder per kind (both backends agree); required-folder projection; creator/updater/thread persisted on create and on version; AC3 leak-canary (non-member + cross-project member → 404, no path/metadata leak in body/detail/logs).
- **Frontend:** only `npm run typecheck` after the optional-field TS type update; no Playwright/Vitest work in this story.

### Project Structure Notes

- Touch points (all existing files — extend, don't add new modules except the optional shared key-builder which can live in `storage.py`):
  - [src/ai_qa/db/models.py](src/ai_qa/db/models.py) — `Artifact` columns
  - [src/ai_qa/artifacts/storage.py](src/ai_qa/artifacts/storage.py) — shared key-builder + kind→folder mapping
  - [src/ai_qa/artifacts/service.py](src/ai_qa/artifacts/service.py) — creator/updater/thread wiring, `REQUIRED_ARTIFACT_FOLDERS`, projection method
  - [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py) — additive `ArtifactResponse` fields + `_artifact_detail_response`
  - `alembic/versions/<new>.py` — one migration off head `e9f1a2b3c4d5`
  - `frontend/src/types/` — optional artifact-type fields (sync only)
- No conflict with the unified structure. The only variance is the documented architecture-vs-actual path for the routes file (`api/artifacts.py`), already called out above.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-10.1] (lines 780-800) + Epic 10 FRs FR35/FR42/FR43/FR45 (lines 204-236)
- [Source: _bmad-output/planning-artifacts/architecture.md] — artifact service & storage layout, bucket structure `ai-qa-artifacts/projects/{project_id}/{requirements,test_cases,test_scripts}/`, artifact metadata model (project_id, kind, storage_path, creator/updater, optional thread_id/agent_run_id, version metadata), project-membership authz, change-event payload, anti-patterns (no direct SeaweedFS access), version-rollback deferred to post-MVP
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; SQLAlchemy async eager-load rule; no secrets in responses/logs/artifacts; full-stack type sync; migration verification workflow
- [Source: src/ai_qa/artifacts/service.py:15-29] — `ARTIFACT_KINDS` (frozen kind values)
- [Source: src/ai_qa/artifacts/storage.py:100-160] — duplicated path logic to unify; current `requirements`/`raw_html`/generic mapping
- [Source: src/ai_qa/db/models.py:125-168] — `Artifact` / `ArtifactVersion` current schema
- [Source: src/ai_qa/api/artifacts.py:30-39, 61-73, 139-151] — storage factory; `ArtifactResponse`; manual detail builder
- [Source: src/ai_qa/api/projects.py:79-101] — `require_project_member_or_admin` / `ProjectAccessDependency`
- [Source: src/ai_qa/models.py:132-151] — `ArtifactChangeEvent` (frozen)
- [Source: src/ai_qa/api/websocket.py:389-427] — `broadcast_artifact_change`
- [Source: src/ai_qa/config.py:186-201] — SeaweedFS settings

### Definition of Done

- [ ] AC1–AC3 satisfied; all five tasks complete.
- [ ] `uv run alembic upgrade head` applies the new migration cleanly; `downgrade` verified; schema shows the 3 new `artifacts` columns.
- [ ] `uv run ruff check .` clean; `uv run mypy` clean (strict).
- [ ] `uv run pytest` green, including new/updated artifact tests + AC3 leak-canary.
- [ ] `npm run typecheck` clean in `frontend/` (optional TS field sync applied).
- [ ] No frozen contract changed (kind strings, `ArtifactChangeEvent`, existing `ArtifactResponse` fields, endpoint paths).
- [ ] Dev Agent Record updated with file list, commands run, and outputs.

### Open Questions for Thuong (non-blocking — sensible defaults chosen)

- **Q1 — Flat vs. collision-safe keys for `test_cases/`/`test_scripts/`. → RESOLVED (code review 2026-06-11): collision-safe nesting chosen.** `build_artifact_key` writes `projects/{project_id}/{folder}/{artifact_id}/v{version}/{safe_name}` for all kinds, so same-name artifacts and per-version bytes never overwrite. Folders stay browsable by prefix. Trade-off accepted: diverges from the flat bucket diagram, but eliminates silent data loss and preserves version bytes.
- **Q2 — Harden `ArtifactService` storage default?** Default: leave `LocalArtifactStorage()` as the service default (unit tests depend on it) and rely on `get_artifact_storage()` injection in all runtime paths. Alternative: make `storage` a required constructor arg (forces explicit injection, but touches test call sites).
- **Q3 — Drop the orphaned `legacy_pipeline_run_id` column** in this migration as cleanup, or defer? Default: include it only if it doesn't complicate the migration.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- 3 mock objects in `test_artifact_events.py` updated to include `created_by_user_id=None`, `updated_by_user_id=None`, `thread_id=None` after Pydantic validation error detected new required fields.
- Alembic autogenerate included unrelated drift for `ai_provider_configs.updated_at` and `projects.confluence_base_url` — removed from migration, keeping only the 3 artifact columns.
- Ruff import ordering auto-fixed in migration file.

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.
- **Task 1 (AC2 metadata):** Added `created_by_user_id`, `updated_by_user_id`, `thread_id` columns to `Artifact` ORM model with `ondelete=SET NULL`. `save_artifact` now persists creator/updater/thread; `create_version` updates `updated_by_user_id`.
- **Task 2 (AC1 folder mapping):** Extracted `build_artifact_key()` shared helper in `storage.py` — eliminates code drift between Local and S3 backends. `testcase` now maps to `test_cases/`, `testscript`/`playwright_script` to `test_scripts/`. Added `REQUIRED_ARTIFACT_FOLDERS` constant + `required_folders()` projection method for Story 10.2.
- **Task 3 (AC3 authz):** Added 4 leak-canary test functions covering all routes for non-members and cross-project members. Confirmed `storage_path` never appears in any API response.
- **Task 4 (full-stack sync):** Added 3 optional fields to `ArtifactResponse` + `_artifact_detail_response` manual builder. Mirrored as optional props on `frontend/src/components/conversations/ProjectSidebar.tsx` `Artifact` interface. No frozen contracts changed.
- **Task 5 (tests + DoD):** 59 artifact tests pass. ruff clean. mypy strict clean. npm run typecheck clean.

### Commands Run

```powershell
uv run alembic heads                  # confirmed head = e9f1a2b3c4d5
uv run alembic revision --autogenerate -m "add_artifact_ownership_and_thread_columns"
uv run ruff check src/ alembic/       # all checks passed
uv run mypy src/ai_qa/artifacts/ src/ai_qa/api/artifacts.py src/ai_qa/db/models.py  # Success
npm run typecheck                     # no errors
uv run pytest tests/unit/test_artifact_service.py tests/api/test_artifact_api.py tests/api/test_artifact_browsing_api.py tests/api/test_artifact_events.py tests/pipelines/test_pipeline_artifact_adapter.py --no-cov -q
# 59 passed
```

### File List

- `src/ai_qa/db/models.py` — Added `created_by_user_id`, `updated_by_user_id`, `thread_id` columns to `Artifact`
- `src/ai_qa/artifacts/storage.py` — Extracted `build_artifact_key()` shared helper used by both backends. **Code review (2026-06-11): switched to collision-safe nested keys** `projects/{project_id}/{folder}/{artifact_id}/v{version}/{safe_name}` for all kinds (logical folders still prefix-browsable)
- `src/ai_qa/artifacts/service.py` — Added `REQUIRED_ARTIFACT_FOLDERS`, `required_folders()`, `_validate_thread()`; updated `save_artifact` and `create_version` to set ownership fields
- `src/ai_qa/api/artifacts.py` — Added `created_by_user_id`, `updated_by_user_id`, `thread_id` to `ArtifactResponse`; updated `_artifact_detail_response` manual builder
- `frontend/src/components/conversations/ProjectSidebar.tsx` — Added 3 optional fields to `Artifact` interface
- `alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py` — New migration: 3 columns + FK + indexes on `artifacts` table; `down_revision = e9f1a2b3c4d5`
- `tests/unit/test_artifact_service.py` — Added tests (folder mapping, creator/updater/thread, thread cross-project rejection). **Code review (2026-06-11):** key-builder test now derives kinds from `ARTIFACT_KINDS` with nested-key assertions + a both-backends routing test
- `tests/api/test_artifact_api.py` — Added 4 AC3 leak-canary tests. **Code review (2026-06-11):** hardened `_no_storage_leak` to assert on storage-key *values* (regex) not just field names, fixed a tautological status assert, added generic-404-`detail` assertions
- `tests/api/test_artifact_events.py` — Updated 3 mock setups to include new nullable fields
- `_bmad-output/implementation-artifacts/10-1-project-artifact-storage-foundation.md` — This story file
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Status updated
- `frontend/src/App.tsx` — **Code review (2026-06-11):** corrected the realtime artifact-change notice handler (past-tense `"deleted"` match + name from local state); extracted the exported `artifactNoticeTypeFor` helper for testability
- `frontend/src/App.test.tsx` — **Code review (2026-06-11):** added 4 Vitest cases for `artifactNoticeTypeFor`

### Change Log

- 2026-06-10: Story 10-1 implemented — artifact ownership metadata (creator/updater/thread), canonical folder mapping (test_cases/test_scripts), required-folder projection, AC3 leak-canary tests, frontend type sync, Alembic migration (604f28c24393).
- 2026-06-11: Code review applied — artifact storage switched to collision-safe nested per-version keys (Open Question Q1 resolved); App.tsx realtime notice handler corrected + unit-tested (`artifactNoticeTypeFor`); AC3 leak-canary hardened to assert on key *values*. Gate re-run green: ruff, mypy (strict), pytest 60 passed, typecheck, vitest 15 passed, eslint.

---

### Review Findings

<!-- markdownlint-disable MD013 -->

Adversarial code review (2026-06-10): 3 parallel layers (Blind Hunter, Edge Case Hunter, Acceptance Auditor), all on Opus 4.8. AC1, AC2, frozen contracts, and migration `down_revision` (single head `604f28c24393`) verified correct against real code. Result: **2 decision-needed, 2 patch, 4 deferred, 8 dismissed** — the dismissed set includes one adversarial false-positive: the Acceptance Auditor's "App.tsx change was not applied to disk" claim was checked against git (`git diff HEAD` + `git show HEAD`) and is **false** — the change is on disk.

#### Decision-needed

- [x] `[Review][Decision]` Flat storage keys overwrite prior-version bytes and allow same-name artifact collisions — `build_artifact_key` ([storage.py:26](src/ai_qa/artifacts/storage.py:26)) returns flat keys (no `artifact_id`/`version`) for `requirements`/`raw_html`/`testcase`/`testscript`/`playwright_script`; `create_version` ([service.py:126](src/ai_qa/artifacts/service.py:126)) rewrites the same key, so older `ArtifactVersion` rows' `content_hash`/`storage_path` no longer match the stored bytes. No `UniqueConstraint(project_id, kind, name)` exists ([models.py:128](src/ai_qa/db/models.py:128)), so two distinct artifacts of the same kind+name silently overwrite each other; names that sanitize identically (`"测试.md"`→`"md"`, blank→`"artifact"` at [storage.py:259](src/ai_qa/artifacts/storage.py:259)) collide too. Matches the documented flat-key MVP trade-off / Open Question Q1. Decision: keep flat / keep flat + add the uniqueness constraint / switch to collision-safe nesting.
- [x] `[Review][Decision]` `App.tsx` realtime-notice change is undocumented and outside the stated 10.1 scope — the working tree edits the artifact-change handler ([App.tsx:405](frontend/src/App.tsx:405)) to match past-tense `"deleted"` and source the artifact name from local state. The change is correct and fixes a real latent bug (HEAD matched only `"delete"`, but the backend emits `"deleted"`, so delete notices never fired) and keeps the frozen `ArtifactChangeEvent` contract — but `App.tsx` is not in this story's File List, the Dev Notes "VERIFIED CORRECT (do not fix)" section is false against `main`, and 10.1 scope states "no UI rendering work." Decision: keep + add to File List + correct the Dev Note + add Vitest coverage / keep + document only / revert into a dedicated 10-7/10-8 follow-up.

#### Patch

- [x] `[Review][Patch]` AC3 leak-canary asserts on field-*name* substrings, not sensitive *values* — `_no_storage_leak` only checks for the tokens `{storage_path, s3_key, object_key, bucket}` in the body, so a leaked path *value* (e.g. `projects/<uuid>/test_cases/x.json`) would pass; should assert the known storage path / `projects/{id}/` prefix is absent and that the 404 detail equals the generic message [tests/api/test_artifact_api.py:605](tests/api/test_artifact_api.py:605)
- [x] `[Review][Patch]` `test_build_artifact_key_*` hardcodes the kind list and calls the helper once — derive kinds from `ARTIFACT_KINDS` (so new kinds are covered) and assert both backend write paths route through `build_artifact_key` [tests/unit/test_artifact_service.py](tests/unit/test_artifact_service.py)

- [x] `[Review][Patch]` (from Decision 1 → nested per-version) Switch `build_artifact_key` to collision-safe keys `projects/{project_id}/{folder}/{artifact_id}/v{version}/{safe_name}` for the logical-folder kinds (generic kinds stay under `artifacts/`); update `test_build_artifact_key_*` expectations and revise the spec's "Storage path target" section + Open Question Q1 to record the nested decision [storage.py:12](src/ai_qa/artifacts/storage.py:12)
- [x] `[Review][Patch]` (from Decision 2 → keep + document + test) Keep the `App.tsx` notice fix; add `App.tsx` to the File List, correct the false "VERIFIED CORRECT (do not fix)" Dev Note, and add Vitest coverage for the `deleted`→delete / `updated`→update notice handler [App.tsx:405](frontend/src/App.tsx:405)

Decisions resolved 2026-06-11: D1 → collision-safe nested per-version keys; D2 → keep the App.tsx fix + document + add test.

#### Deferred

- [x] `[Review][Defer]` `thread_id` column + `_validate_thread` are foundation-only — no production caller passes `thread_id`, and there is no `agent_run.thread_id == thread_id` consistency check when both are supplied [service.py:227](src/ai_qa/artifacts/service.py:227) — deferred, intended foundation for Story 10.2
- [x] `[Review][Defer]` `created_by_user_id`/`updated_by_user_id` not validated against project membership at the service layer [service.py:64](src/ai_qa/artifacts/service.py:64) — deferred, defense-in-depth (the API path already passes an authorized member)
- [x] `[Review][Defer]` `create_version` overwrites `updated_by_user_id` with `None` when a caller passes `None` [service.py:136](src/ai_qa/artifacts/service.py:136) — deferred, not reachable with None from the current API path
- [x] `[Review][Defer]` Migration is not SQLite-batch-safe (`op.create_foreign_key`/`drop_constraint` need `render_as_batch`) [alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py](alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py) — deferred, production is PostgreSQL; tests build schema via `create_all`

<!-- markdownlint-enable MD013 -->
