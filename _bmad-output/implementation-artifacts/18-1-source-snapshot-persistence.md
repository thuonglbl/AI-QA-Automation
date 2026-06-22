---
baseline_commit: 39bec831e2b195b3121a2345a32b282211bd9872
---
# Story 18.1: Per-Run Source Snapshot Persistence

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend only. This is the **foundation** of Epic 18. Each Bob run already fetches every Confluence page / Jira issue into a `ConfluencePage` / `JiraIssue` object ([bob.py:1024-1048](src/ai_qa/agents/bob.py:1024) for Confluence, [bob.py:497-554](src/ai_qa/agents/bob.py:497) for Jira). This story persists a **versioned content snapshot** of each consumed source into a NEW `source_snapshots` table (model `SourceSnapshot`) so that a later run (18.2) has a baseline to diff against. There is **NO existing source-snapshot table** today — `DiscoveredModelSnapshot` ([db/models.py:395-409](src/ai_qa/db/models.py:395)) is the precedent to mirror. No detection, no UI, no cascade in this story — just capture the baseline.

## Story

As the system,
I want each run to persist a versioned snapshot/hash of every Confluence page and Jira issue it consumed,
so that a later run has a baseline to diff against.

## Acceptance Criteria

1. **New `source_snapshots` table + `SourceSnapshot` model.** Given the schema today has no per-source snapshot, when this story is implemented, then a new `SourceSnapshot` model exists in [db/models.py](src/ai_qa/db/models.py) (following the `DiscoveredModelSnapshot` / `TestExecutionResult` conventions — `UUIDPrimaryKeyMixin` + `TimestampMixin`, project + agent_run FKs) with an Alembic migration whose `down_revision` is the current head `273b69541e94`. Columns: `project_id` (FK projects.id CASCADE, indexed, NOT NULL), `agent_run_id` (FK agent_runs.id CASCADE, nullable, indexed), `thread_id` (FK threads.id SET NULL, nullable), `source_type` (String(50) — `"confluence"`/`"jira"`), `source_id` (String(255), indexed — the Confluence page_id or Jira issue_key), `source_url` (Text, nullable), `title` (Text, nullable), `content_hash` (String(128) — SHA-256 hex, same width as `ArtifactVersion.content_hash` at [db/models.py:281](src/ai_qa/db/models.py:281)), `source_version` (String(100), nullable — the cheap secondary change indicator), `snapshot_metadata` (`JSON().with_variant(JSONB, "postgresql")`, nullable — extra fields like `{version, labels, status, jira_updated}`), `retrieved_at` (DateTime(timezone=True), NOT NULL). Add a composite index `(project_id, source_type, source_id)` to make "latest snapshot per source" lookups (18.2) cheap.

2. **One snapshot row per consumed source, per run.** Given a Bob run that consumes N Confluence pages and/or M Jira issues, when the run completes source retrieval, then exactly one `SourceSnapshot` row is written per consumed source, stamped with the run's `agent_run_id` (from `PipelineContext.agent_run_id`, [context.py:20](src/ai_qa/pipelines/context.py:20)), `project_id`, and `thread_id`. A run that consumes the same page twice does not write two rows for it.

3. **Content hash is the universal change indicator.** Given a consumed Confluence page, when its snapshot is written, then `content_hash = sha256(page.content)` (the raw HTML — the same field already persisted via `save_raw_html` at [bob.py:1045](src/ai_qa/agents/bob.py:1045)), computed exactly as the artifact service computes hashes (`hashlib.sha256(content_bytes).hexdigest()`, [service.py:101](src/ai_qa/artifacts/service.py:101)). Given a consumed Jira issue, when its snapshot is written, then `content_hash = sha256(<stable serialization of the issue's requirement-bearing fields>)` — e.g. the `requirement_md` Bob already builds for the issue ([bob.py:1344](src/ai_qa/agents/bob.py:1344) area) or a deterministic concatenation of `summary + description + acceptance_criteria + status`. The serialization MUST be deterministic (stable field order) so an unchanged issue hashes identically across runs.

4. **Capture the cheap secondary version indicator.** Given a Confluence page, when its snapshot is written, then `source_version = str(page.version)` (the `ConfluencePage.version: int | None` field, [pipelines/models.py:39](src/ai_qa/pipelines/models.py:39)) when present, else null; and `snapshot_metadata` carries `{"version": page.version, "labels": page.labels}`. Given a Jira issue, when its snapshot is written, then `source_version` carries the Jira `updated` timestamp if available — see AC5 — else null, and `snapshot_metadata` carries `{"status": issue.status, "jira_updated": <iso8601 or null>}`.

5. **Expose Jira's `updated` timestamp (small reader change).** Given the `JiraIssue` model does NOT currently expose an `updated`/`updated_at` field ([pipelines/models.py:57-103](src/ai_qa/pipelines/models.py:57)), when this story is implemented, then add a nullable `updated_at: datetime | None` field to `JiraIssue` and populate it in `JiraReader._map_issue_data` ([pipelines/jira_reader.py](src/ai_qa/pipelines/jira_reader.py)) from the raw Jira `fields.updated` ISO timestamp (handle both Cloud-flat and DC-fields-nested shapes the mapper already branches on; tolerate absence → null, never raise). This gives Jira a cheap version marker; `content_hash` remains the guaranteed fallback so a missing `updated` never blinds detection.

6. **Persistence never aborts the run.** Given snapshot writing fails for any source (DB error, serialization error), when the error occurs, then it is logged (`logger.warning`, safe fields only — never the raw content or any credential) and the run continues normally — snapshotting is a side-effect of extraction and MUST NOT break requirement extraction (mirrors the best-effort `try/except → warning → continue` contract used throughout Bob, e.g. [bob.py:1093-1116](src/ai_qa/agents/bob.py:1093)). The snapshot write is committed in the same DB session/transaction boundary the artifact saves use (sync session, [[epic-10-artifact-ui-gotchas]]).

7. **Baseline semantics — pre-existing artifacts are "never-checked", not "changed".** Given projects/threads that have artifacts created BEFORE this story shipped (no snapshot rows exist for their sources), when a later run looks for a prior snapshot (18.2), then the absence of any snapshot row means "no baseline yet / never checked" — NOT "changed". This story does NOT backfill historical sources (their original content is not recoverable); it only establishes the baseline going forward. Document this explicitly so 18.2 treats a missing prior snapshot as `new`, never as a false-positive change.

## Tasks / Subtasks

- [ ] **Task 1 — `SourceSnapshot` model + migration (AC: 1)**
  - [ ] Add `class SourceSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base)` to [db/models.py](src/ai_qa/db/models.py) right after `DiscoveredModelSnapshot` ([db/models.py:395](src/ai_qa/db/models.py:395)). Columns + composite index per AC1. Use `JSON().with_variant(JSONB, "postgresql")` for `snapshot_metadata` (mirror `AuditEvent.details` at [db/models.py:311-313](src/ai_qa/db/models.py:311)). Add a `project`/`agent_run` relationship only if needed by a query path; otherwise keep it FK-only to avoid over-eager loading.
  - [ ] Generate the migration: `uv run alembic revision --autogenerate -m "add source_snapshots"`. Confirm `down_revision = "273b69541e94"` (current head — verified via `uv run alembic heads`). Hand-check the generated `op.create_table` against the `a3f8d21c64b9_add_test_execution_results.py` template (UUID PKs, `op.f(...)` FK/index naming via `NAMING_CONVENTION`, `DateTime(timezone=True)`, FK `ondelete` matching the model). Add the composite index `ix_source_snapshots_project_type_source` on `(project_id, source_type, source_id)`.
  - [ ] `uv run alembic upgrade head` locally to confirm the migration applies cleanly, then `uv run alembic downgrade -1` and back up to confirm reversibility.

- [ ] **Task 2 — `SourceSnapshotService` (AC: 2, 3, 6)**
  - [ ] Add a small service (e.g. `src/ai_qa/sources/snapshot_service.py` or alongside the artifact service) with a sync `Session`, exposing `record_snapshot(*, project_id, agent_run_id, thread_id, source_type, source_id, source_url, title, content, source_version, snapshot_metadata) -> SourceSnapshot` that computes `content_hash = hashlib.sha256(_to_bytes(content)).hexdigest()` and inserts the row, and `latest_for_source(*, project_id, source_type, source_id, before_run_id=None) -> SourceSnapshot | None` (18.2 will use the read side — add it now so the table has a reader). Reuse the hashing approach from [service.py:101](src/ai_qa/artifacts/service.py:101); do NOT re-implement `_content_to_bytes` if it can be imported/shared.
  - [ ] Guard every write in `try/except Exception → logger.warning → return None` so AC6 holds. Never log `content`.

- [ ] **Task 3 — Jira `updated_at` field + mapping (AC: 5)**
  - [ ] Add `updated_at: datetime | None = Field(default=None, ...)` to `JiraIssue` ([pipelines/models.py:57](src/ai_qa/pipelines/models.py:57)). If non-null it must be timezone-aware (mirror the `retrieved_at` validator pattern at [pipelines/models.py:93-99](src/ai_qa/pipelines/models.py:93), but allow `None`).
  - [ ] In `JiraReader._map_issue_data` ([pipelines/jira_reader.py](src/ai_qa/pipelines/jira_reader.py)), extract `fields.updated` (Cloud flat / DC nested — match how `status` is already mapped). Parse to a tz-aware datetime; tolerate missing/unparseable → leave null.

- [ ] **Task 4 — Hook snapshot writing into Bob (AC: 2, 3, 4, 6, 7)**
  - [ ] Confluence: in the Phase-1 retrieval loop, after `raw_pages.append(page)` ([bob.py:1048](src/ai_qa/agents/bob.py:1048)) — where the `ConfluencePage` object (with `.version`, `.content`, `.url`, `.title`, `.labels`) is in hand — call `snapshot_service.record_snapshot(...)` with `source_type="confluence"`, `source_id=page.page_id`, `content=page.content`, `source_version=str(page.version) if page.version is not None else None`. This is the right seam because the raw `ConfluencePage` carries the version; the later `self.pages` dicts ([bob.py:1148-1199](src/ai_qa/agents/bob.py:1148)) do NOT carry `version`.
  - [ ] Jira: in `_retrieve_jira_requirements` ([bob.py:497-554](src/ai_qa/agents/bob.py:497)), after the issue is read and before/after the `self.pages.append({... "source_type": "jira" ...})` ([bob.py:534-544](src/ai_qa/agents/bob.py:534)), call `record_snapshot(...)` with `source_type="jira"`, `source_id=issue.issue_key`, `content=<deterministic issue serialization>`, `source_version=issue.updated_at.isoformat() if issue.updated_at else None`, `snapshot_metadata={"status": issue.status, "jira_updated": ...}`.
  - [ ] De-dupe within a single run (AC2): if the same `source_id` is consumed more than once in a run, write only once (e.g. track a `set[str]` of `(source_type, source_id)` already snapshotted this run).
  - [ ] Resolve `agent_run_id`/`project_id`/`thread_id` from `self.project_context` (the `PipelineContext`); assert non-None where the type requires it (Pyrefly-clean, [[project-context]]). Reuse the same session the adapter uses.

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Model/migration: round-trip insert + read a `SourceSnapshot` against the in-memory SQLite test DB; assert the composite index and FK columns exist (the suite builds the schema from models — confirm no `MissingGreenlet`/schema drift). NB: schema drift is invisible to the SQLite suite ([[epic-15-admin-rbac-sprint-change]]) — ALSO verify `alembic upgrade head` applies on a real Postgres-shaped run if available.
  - [ ] Service: `record_snapshot` computes a 64-char SHA-256 hex (`assert len(snap.content_hash) == 64`, mirror [tests for artifact_service]); identical content → identical hash; different content → different hash; a forced DB error → returns None + logs, does not raise (AC6).
  - [ ] Jira mapper: `_map_issue_data` populates `updated_at` from a stubbed Cloud-flat AND DC-nested payload; missing `updated` → null, no raise (AC5).
  - [ ] Bob hook: with a stubbed reader returning 2 Confluence pages (one with `version`, one without) + 1 Jira issue, assert 3 snapshot rows written with the right `source_type`/`source_id`/`source_version`/`content_hash`, stamped with the run's `agent_run_id`; a duplicate page id consumed twice → 1 row (AC2). Mock the MCP/reader, not the DB.
  - [ ] `uv run pytest` (whole suite — coverage gate fails on subset runs, [[backend-test-suite-orphaned-legacy-tests]]). `uv run ruff check --fix src/ tests/` + `uv run ruff format src/ tests/`. `uv run mypy src`.

## Dev Notes

### The one hard fact: there is NO source-snapshot table today

The epic and three forensic sweeps all confirm: `Artifact.agent_run_id` records **generated** artifacts, never the **source pages consumed as input**. Nothing in the schema records "run X read Confluence page Y at content-hash Z". This story creates that record. Without it, 18.2 has nothing to diff. The `DiscoveredModelSnapshot` model ([db/models.py:395-409](src/ai_qa/db/models.py:395)) + its migration `91910492132c` (and the upsert in `admin/model_sync.py::_upsert_model_snapshot`) are the exact precedent — a "last-seen snapshot" written on each run. Mirror its shape; differ only in columns.

### Why hash `page.content` (raw HTML), not the requirement markdown

The requirement `.md` is LLM-generated and non-deterministic — two runs over an identical source can produce slightly different prose, which would create false "changed" signals in 18.2. The raw source (`page.content` for Confluence; the issue's structured fields for Jira) is the deterministic thing that actually changed or didn't. Hash the SOURCE, not the GENERATED output. `source_version` (Confluence version int / Jira `updated`) is the cheap pre-check; `content_hash` is the authoritative one.

### Current behavior to PRESERVE (regression guardrails)

- **Extraction must not regress.** Snapshot writing is a pure side-effect appended to the existing retrieval loops. It must never change `self.pages`, the requirement artifacts, image captioning, or the clarify loop. Wrap it best-effort (AC6).
- **Sync session on the artifact/DB path.** The artifact write path uses a synchronous SQLAlchemy `Session`, not async ([[epic-10-artifact-ui-gotchas]]). Use the same session/commit boundary; do NOT introduce an async session here (no `MissingGreenlet`).
- **No-secret-leak.** Never log raw page content, the MCP credential, request dicts, or full headers — log `.keys()`/safe ids only ([[project-context]]). Snapshot content (page HTML) is the user's source, persisted by design like `raw_html` already is — but credentials never touch the snapshot row.
- **Jira best-effort.** The whole Jira leg is already wrapped best-effort and must stay non-fatal; the new `updated_at` extraction must degrade to null, never raise (AC5/AC6).

### Source tree components to touch

- `src/ai_qa/db/models.py` — **UPDATE** (new `SourceSnapshot` model after line 409).
- `alembic/versions/` — **ADD** (new migration, `down_revision="273b69541e94"`).
- `src/ai_qa/sources/snapshot_service.py` (or alongside `artifacts/service.py`) — **ADD** (`SourceSnapshotService`).
- `src/ai_qa/pipelines/models.py` — **UPDATE** (`JiraIssue.updated_at`).
- `src/ai_qa/pipelines/jira_reader.py` — **UPDATE** (`_map_issue_data` → populate `updated_at`).
- `src/ai_qa/agents/bob.py` — **UPDATE** (record snapshot in Confluence Phase-1 loop ~line 1048 and in `_retrieve_jira_requirements` ~line 534).
- Tests — **ADD** under `tests/` for model, service, Jira mapper, and Bob hook.

### Decided scope (defaults — Thuong, correct if needed)

- **Hash the raw source** (Confluence HTML / deterministic Jira field serialization), not the generated `.md` — avoids false positives from LLM non-determinism.
- **Add `JiraIssue.updated_at`** as the cheap Jira version marker (small bounded reader change); `content_hash` is the universal fallback so it is never load-bearing.
- **No historical backfill.** Pre-existing sources have no snapshot → treated as "never checked" by 18.2, never "changed" (AC7).
- **Snapshot is per-source-per-run** keyed by `(project_id, source_type, source_id)` for the latest-lookup; the table keeps full history (one row per run) so a future audit/timeline can show drift over time.

### Testing standards summary

- Backend pytest; mock the reader/MCP, exercise the real DB models against the in-memory SQLite test DB. Run the WHOLE suite (`--no-cov` only for quick local subset checks; CI runs full).
- No bare `pytest.raises(Exception)` — specific type + `match=`.
- Pyrefly/mypy-clean: assert `PipelineContext` optionals (`project_id`, `agent_run_id`) non-None before passing to non-optional params; bind+assert mock `call_args` before indexing ([[project-context]]).

### Project Structure Notes

- This story OWNS one migration (`source_snapshots`). Story 18.3 owns a SECOND migration (`derived_from_artifact_id` on `artifacts`) that must chain `down_revision` onto THIS story's revision. Stories 18.2/18.4/18.5 add no schema (18.5 reuses the existing `audit_events` table). Sequence migrations carefully if implementing out of order.
- `SourceSnapshot` is foundation-only — no API/WS/FE surface in this story.

### References

- Epic + story: [epics.md#Epic-18](_bmad-output/planning-artifacts/epics.md:2054), [Story 18.1](_bmad-output/planning-artifacts/epics.md:2062)
- Snapshot precedent: [db/models.py:395-409](src/ai_qa/db/models.py:395) (`DiscoveredModelSnapshot`), `91910492132c_add_model_benchmark_scores_and_.py`, `admin/model_sync.py::_upsert_model_snapshot`
- Migration template (add-a-table): `alembic/versions/a3f8d21c64b9_add_test_execution_results.py`; head = `273b69541e94`
- DB conventions: [db/base.py](src/ai_qa/db/base.py) (`Base`, `UUIDPrimaryKeyMixin`, `TimestampMixin`, `NAMING_CONVENTION`)
- Source models: [pipelines/models.py:14-54](src/ai_qa/pipelines/models.py:14) (`ConfluencePage.version`), [pipelines/models.py:57-103](src/ai_qa/pipelines/models.py:57) (`JiraIssue`)
- Bob hook points: [bob.py:1024-1048](src/ai_qa/agents/bob.py:1024) (Confluence Phase-1), [bob.py:497-554](src/ai_qa/agents/bob.py:497) (Jira)
- Content hashing: [artifacts/service.py:101](src/ai_qa/artifacts/service.py:101), `ArtifactVersion.content_hash` [db/models.py:281](src/ai_qa/db/models.py:281)
- Run context: [pipelines/context.py:12-21](src/ai_qa/pipelines/context.py:12), `AgentRun` [threads/models.py:63-79](src/ai_qa/threads/models.py:63)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[artifact-ui-storage-overhaul]], [[epic-10-artifact-ui-gotchas]], [[epic-15-admin-rbac-sprint-change]], [[backend-test-suite-orphaned-legacy-tests]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
