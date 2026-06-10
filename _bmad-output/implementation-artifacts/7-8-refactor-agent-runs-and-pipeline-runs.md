---
baseline_commit: "unknown"
---
# Story 7.8: Refactor Agent Runs and Pipeline Runs

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to refactor and document the differences between agent_runs and pipeline_runs,
So that the transition from the old Pipeline architecture to the new Thread/Chat architecture is clear and artifacts/audits can be correctly migrated.

## Acceptance Criteria

1. **Given** the current transition from Pipeline to Thread/Chat architecture
   **When** reviewing the schema and usage of agent_runs and pipeline_runs
   **Then** the similarities (status tracking, timestamps, metadata) and differences (scope, relationships, audit integration) must be clearly documented
2. **Given** the new Chat interface is finalized
   **When** artifacts and audit events are generated
   **Then** their foreign keys (`pipeline_run_id`) must be updated to use `agent_run_id` (or `thread_id`)
3. **Given** the migration is complete
   **When** the old pipeline components are no longer used
   **Then** `pipeline_runs` should be marked as legacy and eventually removed

## Dev Notes

- **Architecture Patterns and Constraints**:
  - The system is transitioning from a rigid 5-step pipeline architecture (managed by `pipeline_runs`) to a flexible chat/thread-based architecture (managed by `agent_runs`).
  - `pipeline_runs` is scoped at the Project level, while `agent_runs` is scoped at the Thread level.
  - Currently, artifacts are linked to `pipeline_run_id`. As the new Chat interface finalizes, they need to be transitioned to `agent_run_id` or `thread_id`.
  - Audit events are also currently linked to `pipeline_run_id`. They should be transitioned as well.
- **Similarities**:
  - Both track execution status (`pending`, `running`, `completed`, `failed`, `error`).
  - Both store timestamps (`started_at`, `completed_at` for PipelineRun vs `created_at`, `updated_at` for AgentRun).
  - Both store execution metadata (LLM parameters, tokens consumed, provider, model).
- **Differences**:
  - `pipeline_runs` is part of the legacy 5-step process and ties 1-to-many to artifacts directly. It integrates with `audit_events`. It has specific columns for provider and model.
  - `agent_runs` is part of the new Thread Chat structure. It manages message flow logic and doesn't directly link to artifacts yet. It features a natural language `summary` column of the Agent's actions and syncs state back to the Thread.

### References

- [Epic 7: Secure Multi-User Workspace Foundation](file:///_bmad-output/planning-artifacts/epics.md)

## Dev Agent Record

### Agent Model Used

Claude Haiku 4.5

### Debug Log References

- Created by Antigravity handling the `/bmad-create-story` user request.
- 2026-06-04: Verified active ORM schema uses `agent_run_id` for `artifacts` and `audit_events`; `pipeline_runs` is absent from active metadata.
- 2026-06-04: Added regression metadata tests for retired `pipeline_runs` and `agent_runs` FK targets.
- 2026-06-04: Added documentation describing similarities, differences, migration contract, and removal guidance for `agent_runs` vs `pipeline_runs`.
- 2026-06-04: Validation commands: `uv run pytest tests/db/test_models_metadata.py --no-cov` → 5 passed; `uv run pytest tests/db/test_models_metadata.py tests/api/test_artifact_api.py tests/pipelines/test_pipeline_artifact_adapter.py --no-cov` → 13 passed; `uv run pytest tests --no-cov` → 550 passed, 2 skipped; `uv run ruff check tests/db/test_models_metadata.py` → passed.
- 2026-06-04: `uv run ruff check .` still reports pre-existing unrelated lint issues outside the changed Python test file.

### Completion Notes List

- Story context created for refactoring and migrating `pipeline_runs` to `agent_runs`.
- Documented the legacy `pipeline_runs` vs current `agent_runs` architecture, including shared status/metadata concepts and differences in scope, relationships, and audit/artifact linkage.
- Confirmed active artifact and audit schema uses `agent_run_id` and not `pipeline_run_id`.
- Added metadata regression tests to prevent reintroducing active `pipeline_runs` or `pipeline_run_id` references on `artifacts` and `audit_events`.
- Verified related and full backend regression tests pass.

### File List

- `_bmad-output/implementation-artifacts/7-8-refactor-agent-runs-and-pipeline-runs.md` (MODIFIED)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (MODIFIED)
- `alembic/versions/0d5fd025248e_migrate_pipeline_runs_to_agent_runs.py` (MODIFIED)
- `docs/agent-runs-vs-pipeline-runs.md` (NEW)
- `tests/db/test_agent_run_migration.py` (NEW)
- `tests/db/test_models_metadata.py` (MODIFIED)

### Review Findings

- [x] \[Review\]\[Patch\] Destructive migration drops historical artifact/audit linkage — fixed by preserving old `pipeline_run_id` values as `legacy_pipeline_run_id` while adding nullable `agent_run_id` for new relationships.
- [x] \[Review\]\[Patch\] `pipeline_runs` is removed immediately instead of retained as legacy — fixed by retaining `pipeline_runs` and adding legacy retirement marker/note columns instead of dropping the table.
- [x] \[Review\]\[Patch\] Regression tests do not validate data-preserving migration behavior — fixed by adding migration regression tests that prevent dropping legacy linkage/table and verify the new `agent_run_id` relationship migration remains present.

### Change Log

- 2026-06-04: Added agent_runs vs pipeline_runs migration documentation and schema guardrail tests; moved story to review.
- 2026-06-04: Code review patches applied; migration now preserves legacy pipeline references, retains `pipeline_runs` as legacy, and adds migration regression tests; moved story to done.
