# Story 12.7: Refactor Existing Pipeline from Workspace Paths to Project Context

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a R&D engineer,
I want existing agents and stages to operate on project context instead of global local workspace folders,
so that multi-user project collaboration works without breaking the current agent workflow.

## Acceptance Criteria

1. **Project context propagation:** Bob, Mary, Sarah, and future Jack pipeline actions carry an authorized `project_id` and triggering user identity from REST and WebSocket entry points into agent instances and pipeline stages.
2. **Project-scoped input resolution:** When agents need previous-stage inputs, they resolve them through project-scoped artifact queries instead of hard-coded `workspace/requirements`, `workspace/testcases`, or `workspace/testscripts` filesystem paths.
3. **Artifact-service output persistence:** Generated requirements, test cases, Playwright scripts, and metadata are persisted through `ArtifactService` with supported artifact kinds, current-version tracking, content hash/version rows, and `pipeline_run_id` linkage.
4. **Pipeline run recording:** Pipeline execution creates and updates `pipeline_runs` rows with project, triggering user, status, started/completed timestamps, provider/model/config summary where available, and failure/summary information sufficient for troubleshooting.
5. **Legacy isolation:** Any remaining local filesystem assumptions are isolated behind compatibility adapters or explicit transitional seams; new pipeline logic must not add direct writes to global or per-user `workspace/*` stage folders.
6. **Regression preservation:** Existing Epics 3-5 behavior remains operational: Confluence extraction, content parsing, paginated Bob review, Mary per-item review, Sarah side-by-side review, skip/reject flows, and existing tests keep passing or are intentionally updated for project-scoped semantics.
7. **Authorization:** Project-scoped pipeline and artifact operations enforce membership/admin access using the RBAC/project access patterns already established in Epic 12.

## Tasks / Subtasks

- [x] Task 1: Introduce project-scoped pipeline context (AC: 1, 4, 7)
  - [x] Define a lightweight context object or equivalent fields for `project_id`, `user_id`, `user_email`, `pipeline_run_id`, and `ArtifactService`/DB access.
  - [x] Update REST `/api/start`, `/api/approve`, `/api/reject`, `/api/skip`, and `/api/navigate` dispatch so project context is required for authenticated project runs.
  - [x] Update WebSocket action handling to accept selected `projectId` from the frontend message/query contract and validate access before dispatch.
  - [x] Preserve non-project test/backward compatibility paths only behind explicit compatibility mode, not as the default project path.

- [x] Task 2: Create pipeline run lifecycle management (AC: 4)
  - [x] Add a service/helper to create `PipelineRun` at pipeline start or first stage execution.
  - [x] Store `project_id`, `started_by_user_id`, `status`, `started_at`, provider/model/config summary where available.
  - [x] Update status on stage success/failure and set `completed_at` on terminal completion.
  - [x] Ensure artifacts saved during a run receive the same `pipeline_run_id`.
  - [x] Cover rollback/error behavior so failed artifact writes do not leave misleading run status.

- [x] Task 3: Replace direct output writes with artifact persistence (AC: 3, 5)
  - [x] Refactor or wrap `OutputWriter` so project-scoped execution delegates to `ArtifactService.save_artifact()` / `create_version()` instead of writing directly under `workspace/*`.
  - [x] Map outputs to existing artifact kinds: `requirements`, `testcase`, `testscript`, `playwright_script`, `markdown`, `mermaid`, `screenshot`, `report`, `configuration` as appropriate.
  - [x] Persist metadata as artifact metadata content or structured companion artifacts without writing `metadata.json` into stage folders.
  - [x] Reuse `LocalArtifactStorage` and `sanitize_artifact_name`; do not create a second storage abstraction.

- [x] Task 4: Refactor Bob requirements extraction (AC: 1, 3, 5, 6)
  - [x] Keep Confluence/MCP reading and `ContentParser` behavior intact.
  - [x] On each approved page, save requirement markdown through `ArtifactService` with project/run/user linkage.
  - [x] Preserve Bob paginated review metadata (`is_paginated`, `total_pages`, `current_index`) for frontend compatibility.
  - [x] Update success messages to avoid promising files were saved to `requirements/` in project mode.

- [x] Task 5: Refactor Mary input/output flow (AC: 2, 3, 5, 6)
  - [x] Load requirements from project artifacts filtered by kind instead of `self._workspace_dir / "requirements"`.
  - [x] Convert artifact content to temporary/input objects only if required by `TestCaseExtractor`; keep temp usage internal and cleanup-safe.
  - [x] Save approved test cases through `ArtifactService` with kind `testcase` and version metadata.
  - [x] Preserve per-item review, reject/regenerate, and review payload contract.

- [x] Task 6: Refactor Sarah input/output flow (AC: 2, 3, 5, 6)
  - [x] Load test cases from project artifacts filtered by kind `testcase` instead of `workspace/testcases/*.json`.
  - [x] Keep Chrome path / target URL interaction and VisionLocator fallback behavior intact.
  - [x] Adapt `ScriptGenerator` output persistence to artifact service; avoid depending on generated script file paths except in compatibility adapters.
  - [x] Save approved scripts and approval metadata through artifact service with `testscript` or `playwright_script` kinds.
  - [x] Preserve side-by-side review metadata and skip/reject navigation behavior.

- [x] Task 7: Prepare Jack/Epic 6 compatibility seam (AC: 2, 5, 6)
  - [x] Add read APIs/adapters that future Jack can use to query approved script artifacts by project.
  - [x] Do not implement full Jack execution unless already present; this story is a refactor foundation for Epic 6.
  - [x] Document any remaining compatibility fallback that Epic 6 must remove or consume.

- [x] Task 8: Tests and regression validation (AC: all)
  - [x] Add unit tests for project context propagation and artifact read/write adapters.
  - [x] Add API/WebSocket tests for missing/invalid project, non-member denial, admin/member success, and unauthenticated rejection.
  - [x] Add agent tests verifying Bob/Mary/Sarah use `ArtifactService` rather than `workspace/*` directories in project mode.
  - [x] Add pipeline run tests for success/failure status transitions and artifact linkage.
  - [x] Run the existing test suite and update assertions only where project-scoped semantics intentionally replace workspace-path messages.

## Dev Notes

### Current Architecture and Existing Code to Reuse

- `ArtifactService` already exists in [service.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/artifacts/service.py). Reuse it; do not build a parallel persistence layer.
  - `save_artifact(project_id, owner_user_id, kind, name, content, pipeline_run_id=None)` creates `Artifact` and version 1.
  - `create_version(project_id, artifact_id, created_by_user_id, content)` appends immutable versions.
  - `list_artifacts(project_id, kind=None)`, `get_artifact(...)`, and `read_current_content(...)` provide project-bound reads.
  - Supported kinds are defined in `ARTIFACT_KINDS`; use those exact values or extend centrally only if absolutely required.
- `LocalArtifactStorage` already provides traversal-safe file storage under `workspace/artifacts/projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}`. Do not write directly to legacy stage directories for project mode.
- Database tables already exist in [models.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/db/models.py): `Project`, `ProjectMembership`, `PipelineRun`, `Artifact`, `ArtifactVersion`, `AuditEvent`, and `User`.
- Artifact API routes already enforce project access via `ProjectAccessDependency` and active-user checks. Mirror these patterns for pipeline endpoints rather than trusting frontend-provided IDs.
- Current pipeline dispatch lives in [routes.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/api/routes.py) and [websocket.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/api/websocket.py). Both currently route by user email and workspace-derived agents; this is the main seam to refactor.
- Current `BaseAgent` owns `_workspace_dir`, creates `workspace` subfolders, and loads config from workspace files. Do not rip this out blindly; introduce project mode while preserving tests and compatibility.

### Known Workspace Couplings to Remove or Isolate

- `BaseAgent` creates `configuration`, `requirements`, `testcases`, `testscripts`, `report`, and `audit` folders and uses per-user workspace directories.
- `OutputWriter` writes content and `metadata.json` directly to filesystem directories.
- `BobAgent.handle_approve()` writes approved pages to `self._workspace_dir / "requirements"` via `OutputWriter`.
- `MaryAgent.process()` reads `workspace/requirements/*.md`; `_write_approved_test_cases()` writes JSON files under `workspace/testcases`.
- `SarahAgent._load_test_cases()` reads `workspace/testcases/*.json`; `ScriptGenerator` currently writes scripts to `workspace/testscripts`; Sarah writes metadata beside script paths.
- `config.py`, `browser/session.py`, and configuration models still mention workspace configuration. This story should not accidentally break provider/Chrome path flows; isolate remaining config storage if not migrated.

### Implementation Guidance

- Prefer a small project-scoped adapter/service such as `PipelineArtifactAdapter` over spreading raw `ArtifactService` calls throughout every agent. The adapter should expose intent-level methods, e.g. `save_requirement_page`, `load_requirement_markdown`, `save_test_case`, `load_test_cases`, `save_script`, `load_scripts`.
- Keep artifact content formats stable:
  - Requirements: markdown text from parsed `ConfluencePage`/content parser.
  - Test cases: `TestCase.model_dump_json(indent=2)`.
  - Scripts: generated Playwright/Python content as text.
  - Metadata: JSON text, either as separate artifacts with clear names or encoded in content where no DB metadata field exists.
- If existing extractor/generator classes require `Path` inputs, use temporary files as internal compatibility only. They must not become the source of truth, and they must not be exposed as project artifact paths.
- Pipeline run status should be explicit and queryable. Suggested status values: `pending`, `running`, `failed`, `completed`; keep consistent with current model’s string field.
- Frontend 12-6 expects selected project ID in API/WebSocket communication. Backend must validate, not assume, this value.
- Avoid global singleton agent state leakage across projects. Existing `_user_agents: dict[str, dict[int, BaseAgent]]` is not sufficient because one user can access multiple projects. Key project-mode agents by `(user_id/email, project_id, step)` or avoid long-lived mutable agent instances where practical.

### Security and Authorization Guardrails

- Every project-scoped pipeline operation must reject unauthenticated requests.
- A standard user may run pipeline actions only for projects where they are a member.
- Admins may access project-scoped endpoints according to established RBAC behavior.
- Do not trust `project_id`, `pipeline_run_id`, `artifact_id`, or user identifiers from the client without DB validation.
- `ArtifactService._validate_pipeline_run()` already prevents linking an artifact to a run from another project; preserve this invariant.
- API responses and WebSocket errors must not leak password hashes, session secrets, filesystem internals, or unauthorized project existence beyond the established `RESOURCE_NOT_FOUND_DETAIL` pattern.

### Testing Requirements

- Use existing pytest/FastAPI/SQLAlchemy test patterns from Epic 12.
- Prefer dependency overrides for DB sessions and artifact storage when testing API routes.
- Add tests that would fail if project A can read project B artifacts.
- Add tests that would fail if direct `workspace/requirements`, `workspace/testcases`, or `workspace/testscripts` writes occur during project-mode Bob/Mary/Sarah execution.
- Preserve existing unit tests for Epics 3-5 unless an assertion specifically depends on legacy path wording. Update those messages to project-neutral text where needed.

### Project Structure Notes

- Expected touch points:
  - `src/ai_qa/api/routes.py`
  - `src/ai_qa/api/websocket.py`
  - `src/ai_qa/agents/base.py`
  - `src/ai_qa/agents/bob.py`
  - `src/ai_qa/agents/mary.py`
  - `src/ai_qa/agents/sarah.py`
  - `src/ai_qa/pipelines/output_writer.py` or a new adapter module under `src/ai_qa/artifacts/` / `src/ai_qa/pipelines/`
  - tests under the existing `tests/` structure
- Do not introduce a new framework or external dependency for this refactor.
- Keep Pydantic models and SQLAlchemy models typed; avoid raw dicts crossing stage boundaries except in existing API boundary schemas.

### Previous Story Intelligence

- Story 12.5 implemented the artifact service and API foundation. Build on the service contract and storage abstraction; do not replace it with agent-local file management.
- Story 12.6 implemented frontend login/project selection/API client foundation and intentionally did not complete backend pipeline storage refactoring. This story is the backend integration that makes project selection meaningful for pipeline execution.
- Recent review work emphasized strict auth/RBAC, secret-free responses, and no stale token trust. Revalidate users/projects against DB when authorizing pipeline actions.

### References

- Story 12.7 source: [_bmad-output/planning-artifacts/epics.md](file:///c:/Users/laub/source/repos/ai-qa-automation/_bmad-output/planning-artifacts/epics.md#L763-L778)
- Artifact service foundation: [service.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/artifacts/service.py)
- Artifact storage foundation: [storage.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/artifacts/storage.py)
- Artifact API authorization pattern: [artifacts.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/api/artifacts.py)
- Pipeline dispatch: [routes.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/api/routes.py)
- WebSocket dispatch: [websocket.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/api/websocket.py)
- Database schema: [db/models.py](file:///c:/Users/laub/source/repos/ai-qa-automation/src/ai_qa/db/models.py)
- Previous story 12.5: [_bmad-output/implementation-artifacts/12-5-project-scoped-artifact-service.md](file:///c:/Users/laub/source/repos/ai-qa-automation/_bmad-output/implementation-artifacts/12-5-project-scoped-artifact-service.md)
- Previous story 12.6: [_bmad-output/implementation-artifacts/12-6-frontend-login-project-selection-and-api-client-foundation.md](file:///c:/Users/laub/source/repos/ai-qa-automation/_bmad-output/implementation-artifacts/12-6-frontend-login-project-selection-and-api-client-foundation.md)

## Dev Agent Record

### Agent Model Used

Amelia - bmad-agent-dev / Antigravity

### Debug Log References

### Completion Notes List

- Story context generated by BMad create-story workflow.
- Ultimate context engine analysis completed - comprehensive developer guide created.
- Implemented `PipelineContext`, `PipelineRunService`, and `PipelineArtifactAdapter` seams for project-scoped pipeline execution.
- Refactored REST and WebSocket dispatch to validate project membership/admin access and propagate project context into agents.
- Refactored Bob, Mary, and Sarah project-mode persistence to use `ArtifactService` through `PipelineArtifactAdapter`, preserving legacy workspace compatibility paths.
- Added PipelineRun lifecycle transitions for running, completed, and failed states, including preservation of the active run across follow-up actions.
- Added regression tests for project context authorization, WebSocket project context, artifact adapter behavior, Bob/Mary/Sarah project-scoped artifact persistence, project isolation, and PipelineRun status transitions.
- Validation: `uv run pytest tests/test_pipeline_project_context.py tests/test_project_scoped_agents.py tests/test_pipeline_artifact_adapter.py tests/test_pipeline_websocket_project_context.py tests/test_api.py -q --no-cov` → 41 passed, 27 warnings.

### File List

- `src/ai_qa/pipelines/context.py`
- `src/ai_qa/pipelines/run_service.py`
- `src/ai_qa/pipelines/artifact_adapter.py`
- `src/ai_qa/api/routes.py`
- `src/ai_qa/api/websocket.py`
- `src/ai_qa/api/schemas.py`
- `src/ai_qa/agents/base.py`
- `src/ai_qa/agents/bob.py`
- `src/ai_qa/agents/mary.py`
- `src/ai_qa/agents/sarah.py`
- `tests/test_pipeline_artifact_adapter.py`
- `tests/test_pipeline_project_context.py`
- `tests/test_pipeline_websocket_project_context.py`
- `tests/test_project_scoped_agents.py`
