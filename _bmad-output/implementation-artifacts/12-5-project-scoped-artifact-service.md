# 12-5: Project-Scoped Artifact Service

## Header

```yaml
story_id: 12.5
story_key: 12-5-project-scoped-artifact-service
epic: Epic 12 - Decoupled Backend, Database, Auth, and Project Foundation
status: done
created_by: BMad Story Agent
created_at: 2026-05-07
story_title: Project-Scoped Artifact Service
epic_title: Decoupled Backend, Database, Auth, and Project Foundation
epic_description: Pivot from single-user file-based workspace storage to a decoupled multi-user system with React frontend, FastAPI backend, PostgreSQL source of truth, and project-scoped artifacts.
```

## Requirements

### User Story

**As a** project member,  
**I want** generated Markdown, Mermaid, and script files to be linked to a project,  
**So that** everyone in the same project can review and edit shared AI outputs.

### Acceptance Criteria (BDD)

**Scenario 1: Artifact metadata is persisted with project ownership**
```gherkin
Given an active project member has a project they can access
When the artifact service saves Markdown, Mermaid, Playwright script, screenshot, or report output
Then an artifacts row is stored with project_id, artifact kind, name, storage_path, current_version, timestamps, and optional pipeline_run_id
And the initial artifact_versions row is stored with version 1, content_hash, storage_path, created_by_user_id, and timestamps
And response schemas expose only safe artifact metadata, not raw ORM relationship graphs
```

**Scenario 2: Large content is stored through a local storage abstraction**
```gherkin
Given artifact content is provided as text or bytes
When the artifact service persists the artifact
Then content is written through a LocalArtifactStorage abstraction instead of direct agent filesystem writes
And the persisted storage key/path is deterministic enough to locate the artifact but safe from path traversal
And atomic or temp-file write behavior prevents corrupt partial output on write failures
And the storage interface can later be replaced by MinIO or S3-compatible storage without changing callers
```

**Scenario 3: Artifact versions preserve edit history**
```gherkin
Given an artifact already exists in a project
When a project member saves edited content for that artifact
Then a new artifact_versions row is appended with version current_version + 1
And the artifact current_version and storage_path point to the newest version
And earlier versions remain queryable and unchanged
And content_hash changes when content changes
```

**Scenario 4: Project membership gates artifact access**
```gherkin
Given project-scoped artifact endpoints or service methods are available
When a standard user requests artifacts for a project where they are not a member
Then the backend rejects the request without returning artifact data or revealing hidden project details
And admins may access artifact metadata for any project
And unauthenticated, deleted, inactive, or stale users are rejected consistently
```

**Scenario 5: Agents consume an artifact service contract rather than hard-coded workspace paths**
```gherkin
Given future Bob, Mary, Sarah, and Jack refactors need to save or read generated outputs
When they integrate with project-scoped storage
Then they can call a cohesive artifact service API to save, list, read, and version artifacts
And the legacy OutputWriter remains available only as a compatibility boundary until Story 12.7 removes or adapts workspace-path usage
And the service API supports artifact type filters needed by downstream stages
```

## Developer Context

### Epic 12 Context and Boundaries

Epic 12 is converting the product from a single-user `workspace/` folder into a multi-user, project-scoped backend. Stories 12.1-12.4 already established SQLAlchemy/Alembic persistence, local auth, RBAC, admin APIs, project listing/detail APIs, and a reusable project membership guard.

This story creates the backend artifact persistence layer that later pipeline stories can call. It should provide an implementation-ready service and minimal protected API surface for artifact metadata/content, but it must not refactor Bob/Mary/Sarah/Jack end-to-end yet.

**Do implement:**
- A cohesive artifact domain module/service that persists `Artifact` and `ArtifactVersion` rows.
- A local artifact storage abstraction for file contents, with safe paths and replaceable interface.
- Protected project-scoped artifact list/detail/read/save/version behavior.
- Membership/admin authorization by reusing Story 12.4 project access helpers.
- Tests for metadata persistence, content storage, version increments, authorization, path traversal, and failure cleanup.

**Do not implement:**
- Full pipeline refactor away from `workspace/` paths; Story 12.7 owns that migration.
- Frontend project artifact browser/editor; Story 12.6 and later UX stories own UI.
- MinIO/S3 integration; only design the interface so it can be swapped later.
- Audit event expansion; Epic 9 owns comprehensive audit integration.
- Pipeline run orchestration beyond accepting optional `pipeline_run_id` when saving artifacts.

### Existing Codebase Intelligence

Relevant current files and patterns:

```text
src/ai_qa/
├── api/
│   ├── app.py                    # includes api, projects, admin, auth routers
│   ├── projects.py               # ProjectResponse + require_project_member_or_admin
│   ├── admin.py                  # admin user/project/membership routes
│   └── auth/
│       ├── local.py              # get_db_session_dependency
│       ├── middleware.py         # protects /api/* and /ws; docs routes are public
│       └── rbac.py               # get_current_active_user(), require_admin()
├── db/
│   ├── models.py                 # Project, ProjectMembership, PipelineRun, Artifact, ArtifactVersion
│   └── session.py                # SQLAlchemy session helpers
├── pipelines/
│   └── output_writer.py          # legacy filesystem writer with atomic temp-file pattern
└── models.py                     # StageResult and shared Pydantic models

tests/
├── test_project_api.py           # project membership/API patterns from 12.4
├── test_admin_rbac_api.py        # admin/RBAC patterns from 12.3
└── db/                           # DB model/session tests
```

Important model facts from `src/ai_qa/db/models.py`:
- `Artifact` already has `project_id`, optional `pipeline_run_id`, `kind`, `name`, `storage_path`, `current_version`, timestamps, and `versions` relationship.
- `ArtifactVersion` already has `artifact_id`, `version`, `content_hash`, optional `storage_path`, optional `created_by_user_id`, and unique `(artifact_id, version)` constraint.
- `Project.artifacts` and `PipelineRun.artifacts` relationships already exist.
- `Artifact` has index `ix_artifacts_project_kind`; use it for project+kind filters.
- `ArtifactVersion.content_hash` length is 128 chars; SHA-256 hex fits.

### Architecture and Security Guardrails

- Backend remains FastAPI under `src/ai_qa/api`; include new routes from `create_app()` in `src/ai_qa/api/app.py` under `/api`.
- Use SQLAlchemy 2.x ORM, Pydantic schemas, and explicit response models. Do not return raw ORM graphs.
- Reuse `get_current_active_user()` for identity revalidation and `require_project_member_or_admin()` for project membership. Do not trust JWT payloads alone.
- Use generic error details for unauthorized access:
  - unauthenticated, invalid, deleted, inactive, stale identity: `401` generic auth detail;
  - authenticated but not allowed: `404 Resource not found` or generic `403 Forbidden`, but choose one and test it consistently;
  - missing artifact after project access succeeds: safe `404`.
- Prevent path traversal. Treat artifact names and storage keys as untrusted input; never join raw user-provided path segments directly to a storage root.
- Store content on local disk through a storage interface, not directly in agents. Keep the interface narrow enough to swap for object storage later.
- Avoid leaking hidden project or artifact existence to non-members.
- Preserve data sovereignty: no external storage or network calls.

### Recommended Implementation Shape

Suggested new modules:

```text
src/ai_qa/artifacts/
├── __init__.py
├── service.py       # ArtifactService: save/list/get/read/create_version
└── storage.py       # ArtifactStorage protocol + LocalArtifactStorage

src/ai_qa/api/artifacts.py
```

Suggested storage interface:

```python
class ArtifactStorage(Protocol):
    def write(self, *, project_id: UUID, artifact_id: UUID, version: int, name: str, content: str | bytes) -> str: ...
    def read(self, storage_path: str) -> bytes: ...
```

Suggested service methods:

```python
class ArtifactService:
    def save_artifact(
        self,
        *,
        project_id: UUID,
        owner_user_id: UUID | None,
        kind: str,
        name: str,
        content: str | bytes,
        pipeline_run_id: UUID | None = None,
    ) -> Artifact: ...

    def create_version(
        self,
        *,
        artifact: Artifact,
        created_by_user_id: UUID | None,
        content: str | bytes,
    ) -> Artifact: ...

    def list_artifacts(self, *, project_id: UUID, kind: str | None = None) -> list[Artifact]: ...
    def get_artifact(self, *, project_id: UUID, artifact_id: UUID) -> Artifact | None: ...
    def read_current_content(self, artifact: Artifact) -> bytes: ...
```

Suggested API endpoints under `/api/projects/{project_id}/artifacts`:

- `GET /api/projects/{project_id}/artifacts`
  - Authenticated project members/admins only.
  - Optional `kind` query filter.
  - Return artifact metadata list with `id`, `project_id`, `kind`, `name`, `current_version`, `created_at`, `updated_at`, and maybe `pipeline_run_id`.

- `POST /api/projects/{project_id}/artifacts`
  - Authenticated project members/admins only.
  - Request: `kind`, `name`, `content`, optional `pipeline_run_id`, optional `content_encoding` (`text` or `base64`) if bytes support is exposed through JSON.
  - Creates artifact and version 1.
  - Return metadata for created artifact.

- `GET /api/projects/{project_id}/artifacts/{artifact_id}`
  - Return metadata and version summaries after project access succeeds.

- `GET /api/projects/{project_id}/artifacts/{artifact_id}/content`
  - Return current content. For simple JSON-first implementation, returning UTF-8 text content is acceptable for Markdown/Mermaid/scripts/reports; binary screenshot support may remain service-level or use base64 in API.

- `POST /api/projects/{project_id}/artifacts/{artifact_id}/versions`
  - Append a new version with edited content.
  - Return updated metadata/current_version.

Implementation expectations:
- Validate `kind` against known values such as `markdown`, `mermaid`, `playwright_script`, `screenshot`, `report`, `requirements`, `testcase`, `testscript`, `configuration`; keep list centralized.
- Validate non-empty, reasonable-length names. Derive storage filenames from sanitized names plus artifact/version IDs to avoid collisions.
- Hash exact bytes written with SHA-256 and persist the hex digest.
- Use DB transaction ordering carefully. If file write succeeds but DB commit fails, clean up the just-written file when possible. If DB flush is needed for UUIDs, flush before storage write, then commit after both artifact and version rows are ready.
- For local storage root, prefer settings-driven configuration if already available; otherwise choose a clearly named project-local default such as `workspace/artifacts/` and document it. Do not store runtime artifacts in `_bmad-output`.
- Keep legacy `OutputWriter` intact; optionally add adapter tests or notes, but do not break completed Epics 3-5.

### Previous Story Intelligence (12.4)

Story 12.4 added:
- `src/ai_qa/api/projects.py` with `/api/projects` and `/api/projects/{project_id}`.
- `require_project_member_or_admin(project_id, current_user, db)` that returns a project only for admins or members.
- Admin all-project visibility and standard-user project filtering.
- OpenAPI/docs routes left public while `/api/*` remains protected.
- API tests covering admin/member/outsider/unauthenticated/stale-user access.

Review lessons to preserve:
- Revalidate active users through RBAC dependencies; do not rely only on middleware `request.state.user`.
- Avoid hidden-project leaks for non-members.
- Use Pydantic response schemas to prevent password hashes, tokens, and raw ORM internals from leaking.
- Reuse existing test fixture patterns from `tests/test_project_api.py` and `tests/test_admin_rbac_api.py`.
- Full regression previously passed with `.\.venv\Scripts\python.exe -m pytest --no-cov` (`462 passed, 2 skipped`).

### Git Intelligence

Recent commits show the current implementation direction:

```text
4aee719 fix security scan from Bitbucket
ef655c1 feat 12-4: Project and Membership Management API
db1a9ab feat 12-3: Role-Based Access Control for Admin and Standard Users
172b73b refactor: 12-2: Local Authentication and Admin Bootstrap
```

The latest security commit indicates secret-scan remediation is active. Do not add example credentials, real Basic auth values, tokens, or secret-looking strings in docs, tests, or fixtures.

## Tasks / Subtasks

- [x] Add artifact storage abstraction. (AC: 2)
  - [x] Create `src/ai_qa/artifacts/storage.py` with `ArtifactStorage` protocol and `LocalArtifactStorage` implementation.
  - [x] Sanitize names/paths and prevent traversal; test malicious names like `../secret.txt` and Windows separators.
  - [x] Use temp-file then atomic replace for local writes, following the safe pattern in `OutputWriter`.
- [x] Add artifact service layer. (AC: 1, 2, 3, 5)
  - [x] Create `src/ai_qa/artifacts/service.py` with save/list/get/read/version methods.
  - [x] Persist `Artifact` and initial `ArtifactVersion` rows with SHA-256 content hash.
  - [x] Append versions without mutating previous `ArtifactVersion` rows.
  - [x] Keep optional `pipeline_run_id` support and validate it belongs to the same project when supplied.
- [x] Add project-scoped artifact API schemas and routes. (AC: 1, 3, 4, 5)
  - [x] Create `src/ai_qa/api/artifacts.py` and include it in `api/app.py` under `/api`.
  - [x] Implement list/create/detail/read-content/create-version routes under `/api/projects/{project_id}/artifacts`.
  - [x] Use explicit Pydantic request/response models; publish schemas in OpenAPI.
- [x] Enforce project authorization. (AC: 4)
  - [x] Reuse `require_project_member_or_admin` for all artifact routes.
  - [x] Ensure standard users cannot list/read/version artifacts in projects where they are not members.
  - [x] Ensure admins can access artifact metadata/content for any project.
  - [x] Keep unauthenticated and stale-user behavior consistent with existing auth tests.
- [x] Preserve legacy pipeline compatibility. (AC: 5)
  - [x] Leave `OutputWriter` behavior intact for completed Epics 3-5.
  - [x] Provide a clear service contract Story 12.7 can call when replacing hard-coded `workspace/` reads/writes.
  - [x] Avoid broad agent refactors in this story.
- [x] Add automated tests. (AC: 1, 2, 3, 4, 5)
  - [x] Unit-test storage write/read, sanitization, hashing, and temp-file cleanup.
  - [x] Service-test metadata persistence, initial version, subsequent version, and version history.
  - [x] API-test member/admin access, non-member denial, unauthenticated rejection, OpenAPI visibility, kind filtering, artifact not found, and optional pipeline_run_id validation.
  - [x] Regression-test no password hashes/tokens/raw ORM internals in artifact responses.

### Review Findings

- [x] [Review][Patch] Make artifact version creation concurrency-safe [src/ai_qa/artifacts/service.py:100]
- [x] [Review][Patch] Remove internal storage keys from public artifact response schemas [src/ai_qa/api/artifacts.py:51]
- [x] [Review][Patch] Make version creation service contract project-scoped [src/ai_qa/artifacts/service.py:92]
- [x] [Review][Patch] Prevent cleanup race for failed concurrent version writes [src/ai_qa/artifacts/service.py:104]
- [x] [Review][Patch] Return controlled API errors for missing/unavailable artifact content [src/ai_qa/api/artifacts.py:232]
- [x] [Review][Patch] Add content size limits for artifact create/version requests [src/ai_qa/api/artifacts.py:82]
- [x] [Review][Patch] Map version append validation failures consistently [src/ai_qa/api/artifacts.py:256]
- [x] [Review][Patch] Add tests that historical version content remains readable [tests/test_artifact_service.py:111]
- [x] [Review][Patch] Add rollback cleanup coverage for create_version [tests/test_artifact_service.py:216]

## Out of Scope

- React artifact browser/editor or project picker UI.
- End-to-end agent pipeline conversion from workspace folders to project context.
- MinIO, S3, Azure Blob, or any network object storage implementation.
- Full audit log integration for artifact reads/writes.
- Artifact deletion, restore, branching, comments, approvals, or conflict resolution.
- Enterprise SSO changes.

## Project Context Reference

- `_bmad-output/planning-artifacts/epics.md`, Epic 12 and Story 12.5: artifact metadata in PostgreSQL, local storage abstraction, version history, and agent access through service rather than hard-coded workspace paths.
- `_bmad-output/planning-artifacts/architecture.md`: FastAPI, SQLAlchemy 2.x, Pydantic schemas, local/on-prem data sovereignty, safe output writing, and pytest/Ruff/mypy standards.
- `_bmad-output/implementation-artifacts/12-4-project-and-membership-management-api.md`: reusable project membership authorization and project API patterns.
- `src/ai_qa/db/models.py`: authoritative `Artifact` and `ArtifactVersion` ORM schema.
- `src/ai_qa/api/projects.py`: `require_project_member_or_admin` helper to reuse for project-scoped artifact routes.
- `src/ai_qa/pipelines/output_writer.py`: legacy atomic local output writer pattern to preserve and learn from.

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro

### Debug Log References

- 2026-05-07T16:06:59+07:00 - Started Story 12.5 and moved sprint status to in-progress.
- 2026-05-08T09:41:41+07:00 - Artifact-focused tests passed: `tests/test_artifact_service.py tests/test_artifact_api.py` (12 passed).
- 2026-05-08T09:42:05+07:00 - Regression subset passed: artifact service/API plus project API tests (18 passed).
- 2026-05-08T09:43:29+07:00 - Full regression passed with `.\.venv\Scripts\python.exe -m pytest --no-cov` (474 passed, 2 skipped).
- 2026-05-08T09:43:33+07:00 - Ruff validation passed for changed artifact/API/model/test files.

### Completion Notes List

- Implemented `ArtifactStorage` protocol and `LocalArtifactStorage` with deterministic project/artifact/version storage keys, name sanitization, traversal protection, temp-file writes, atomic replace, read, and best-effort delete cleanup.
- Implemented `ArtifactService` save/list/get/read/create-version contract with centralized kind validation, SHA-256 hashes, immutable version rows, current-version metadata updates, and same-project `pipeline_run_id` validation.
- Added protected project-scoped artifact API routes for list/create/detail/current-content/create-version under `/api/projects/{project_id}/artifacts` using explicit Pydantic schemas and `require_project_member_or_admin` authorization.
- Supported JSON-safe text and base64 content exchange for API callers while preserving bytes support at the service/storage layer.
- Preserved legacy `OutputWriter` behavior and avoided broad Bob/Mary/Sarah/Jack refactors; Story 12.7 can consume the new `ArtifactService` contract.
- Adjusted `PipelineRun.config_summary` mapping to use generic SQLAlchemy `JSON` with PostgreSQL `JSONB` variant so existing SQLite-based test fixtures can create tables that include pipeline runs.

### File List

- `src/ai_qa/api/app.py`
- `src/ai_qa/api/artifacts.py`
- `src/ai_qa/artifacts/__init__.py`
- `src/ai_qa/artifacts/service.py`
- `src/ai_qa/artifacts/storage.py`
- `src/ai_qa/db/models.py`
- `tests/test_artifact_api.py`
- `tests/test_artifact_service.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/12-5-project-scoped-artifact-service.md`

## Story Completion Status

```yaml
status: review
completion_notes: |
  Story 12.5 implementation complete. Project-scoped artifact storage, service, API routes, authorization, versioning, and automated tests are in place. Full regression passed with 474 passed and 2 skipped; Ruff passed for changed files.
```
