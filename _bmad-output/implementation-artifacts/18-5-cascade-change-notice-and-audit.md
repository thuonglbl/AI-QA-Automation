---
baseline_commit: 39bec831e2b195b3121a2345a32b282211bd9872
---
# Story 18.5: Change Notice, Realtime Signal, and Audit Trail

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Full-stack, cross-cutting. Surfaces what 18.2/18.4 detect and decide so the whole team — not just the user driving the run — knows sources drifted and what was regenerated. Three legs: (1) a **change notice** chat message, (2) a project-scoped **realtime event** so other open clients refresh/notice, and (3) an **audit trail** record of the source-change and cascade decisions. **Key finding that corrects the epic/roadmap assumption:** the `AuditEvent` model + `audit_events` table ALREADY EXIST in the live schema ([db/models.py:291-318](src/ai_qa/db/models.py:291); table created in `20260504_1201_initial_core_schema.py`) with `user_id`/`project_id`/`agent_run_id`/`event_type`/`resource_type`/`resource_id`/`details` columns and relationships wired on `User`/`Project`/`AgentRun`. So 18.5 can WRITE audit events with no migration and **no dependency on Epic 20** — there is just no audit *service* yet (Epic 20 builds the read/view side).

## Story

As a project member,
I want detected source changes and cascade decisions surfaced as a notice/realtime event and recorded in the audit trail,
so that the team knows when sources drifted and what was regenerated.

## Acceptance Criteria

1. **Change notice in the conversation.** Given a source change is detected (18.2) or a cascade decision is made (18.4), when it happens, then a concise English notice message is posted to the thread (`sender="system"` or `"agent"`, `message_type` `info`/`warning`) summarizing the event — e.g. `"Source 'Login Spec' changed (v4 → v7). 3 downstream assets may be stale."` and, on a decision, `"Cascade re-run confirmed through Scripts."` / `"Cascade declined."`. Notices reuse the existing message infrastructure (`AgentMessage`, [models.py:74-132](src/ai_qa/models.py:74); system-message precedent at [threads/service.py:308-314](src/ai_qa/threads/service.py:308)). English only ([[app-ui-english-only]]).

2. **Project-scoped realtime signal.** Given a source change is detected, when the notice is created, then a realtime event is broadcast to all WS clients who are members of that project, so other open sessions/threads can refresh or show a drift indicator. Reuse the existing project-scoped broadcast pattern — `broadcast_artifact_change` ([api/websocket.py:488-533](src/ai_qa/api/websocket.py:488)) already delivers only to connections whose `member_project_ids` includes the project. Add a parallel `source_change` event (a new `SourceChangeEvent` Pydantic model alongside `ArtifactChangeEvent` at [models.py:134-154](src/ai_qa/models.py:134), or an extra `change_type` on a shared event) carrying `{project_id, source_type, source_id, status, changed_count}` — never raw content.

3. **Audit record for source-change detection.** Given a source change is detected, when detection completes, then an `AuditEvent` row is written ([db/models.py:291-318](src/ai_qa/db/models.py:291)) with `event_type="source_change_detected"`, `project_id`, `agent_run_id` (the detecting run), `user_id` (the acting user), `resource_type="source"`, `resource_id=<source_id>`, and `details={"source_type","source_url","prior_version","current_version","prior_hash_prefix","current_hash_prefix","changed_count"}`. `details` uses the JSON column as-is ([db/models.py:311-313](src/ai_qa/db/models.py:311)); NEVER store raw content or any credential.

4. **Audit record for cascade decisions + outcomes.** Given a cascade is confirmed or declined (18.4), when the decision is made, then an `AuditEvent` is written with `event_type` in `{"cascade_confirmed","cascade_declined"}`, `details={"scope": <depth>, "impact_counts": {...}, "source_id": ...}`, keyed to the same `agent_run_id`. As the guided cascade regenerates each stage, when a stage completes, then an `AuditEvent` `event_type="cascade_stage_regenerated"` is written with `details={"stage": "requirements|test_cases|scripts|execution", "regenerated_ids": [...]}`. All cascade events share the `agent_run_id` so the trail is reconstructable as one batch.

5. **Thin `AuditService` (no migration).** Given there is no audit-writing service today (only the model/table), when this story is implemented, then a minimal `AuditService.record(*, db, user_id, project_id, agent_run_id, event_type, resource_type=None, resource_id=None, details=None)` is added that inserts an `AuditEvent` (setting `created_at = datetime.now(UTC)` — the model has no `TimestampMixin`, only a bare `created_at`, [db/models.py:314](src/ai_qa/db/models.py:314)). Writing audit is best-effort: a failure logs a warning and never breaks detection/cascade (AC7).

6. **Frontend drift indicator from the realtime event.** Given the FE receives a `source_change` realtime event for the active project, when it arrives, then the FE shows an unobtrusive drift indicator/notice (and may refresh relevant views), reusing the existing raw-event handler that already processes `artifact_change` ([App.tsx:480-516](frontend/src/App.tsx:480)). Add a branch for the new event type. No blocking modal; English only; add the TS type for the event ([[project-context]] full-stack-sync).

7. **All three legs are best-effort and side-effect-isolated.** Given notice/broadcast/audit each can fail independently, when any one fails, then it is caught, logged (safe fields only), and the others + the core detection/cascade proceed unaffected — exactly like the existing `broadcast_artifact_change` call sites wrap the publish in best-effort `try/except` ([api/artifacts.py:327-328](src/ai_qa/api/artifacts.py:327)). No leg may abort a run.

## Tasks / Subtasks

- [ ] **Task 1 — `AuditService` (AC: 3, 4, 5, 7)**
  - [ ] Add `src/ai_qa/audit/service.py` with `AuditService.record(...)` inserting an `AuditEvent` (sync `Session`; set `created_at=datetime.now(UTC)` since the model lacks `TimestampMixin` — confirm at [db/models.py:291-314](src/ai_qa/db/models.py:291)). Best-effort `try/except → logger.warning` (AC7). Provide tiny helpers/constants for the `event_type` vocabulary (`source_change_detected`, `cascade_confirmed`, `cascade_declined`, `cascade_stage_regenerated`).
  - [ ] Do NOT build the admin read/view UI — that is Epic 20 (20-3 admin audit trail view). This story only WRITES events into the existing table.

- [ ] **Task 2 — Source-change notice + audit (AC: 1, 3)**
  - [ ] In the 18.2 detection flow, after the `source_change_report` is built, post the human notice message (AC1) and call `AuditService.record(event_type="source_change_detected", ...)` per AC3. Only for `changed` sources (a `new`/`unchanged` source needs no notice/audit, or at most a debug log).

- [ ] **Task 3 — `SourceChangeEvent` realtime broadcast (AC: 2, 7)**
  - [ ] Add `SourceChangeEvent` Pydantic model near `ArtifactChangeEvent` ([models.py:134-154](src/ai_qa/models.py:134)) with `{type:"source_change", project_id, source_type, source_id, status, changed_count, timestamp}` (no content/secrets).
  - [ ] Add `broadcast_source_change(project_id, ...)` next to `broadcast_artifact_change` ([api/websocket.py:488-533](src/ai_qa/api/websocket.py:488)), reusing the SAME member-project delivery filter (only send to connections whose `member_project_ids` includes the project). Call it from the detection flow, best-effort (AC7).

- [ ] **Task 4 — Cascade decision + stage audit (AC: 4)**
  - [ ] In 18.4's `_handle_cascade_confirm`, write `cascade_confirmed`/`cascade_declined` on the decision and `cascade_stage_regenerated` as each guided stage completes, all sharing the cascade's `agent_run_id`. Post the matching English notice messages (AC1).

- [ ] **Task 5 — Frontend drift indicator (AC: 6)**
  - [ ] In the raw-event handler ([App.tsx:480-516](frontend/src/App.tsx:480)) add a branch for `data.type === "source_change"`: show a dismissible drift notice for the active project (and optionally bump a refresh trigger). Add the TS type in `frontend/src/types/`. English; `npm run typecheck` + `npm run build`.

- [ ] **Task 6 — Tests (all ACs)**
  - [ ] `AuditService.record` inserts a row with the right `event_type`/`resource_id`/`details` and a tz-aware `created_at`; a forced DB error → logs + returns, no raise (AC5/AC7). NEVER persists content/secrets (assert `details` has only the whitelisted keys).
  - [ ] Detection flow: a `changed` source writes ONE `source_change_detected` audit row + posts a notice + broadcasts a `source_change` event to a project member but NOT to a non-member connection (reuse the broadcast filter test pattern); `unchanged`/`new` writes none.
  - [ ] Cascade flow: confirm writes `cascade_confirmed` + per-stage `cascade_stage_regenerated` sharing one `agent_run_id`; decline writes `cascade_declined` and regenerates nothing (cross-check 18.4 AC2).
  - [ ] Best-effort isolation: make the broadcast raise → detection + audit still succeed; make audit raise → notice + broadcast still succeed (AC7).
  - [ ] FE Vitest: `source_change` event renders the drift notice for the active project, ignored for another project; English strings; dismissible.
  - [ ] `uv run pytest` (full suite) + ruff + `mypy src`; `npm run typecheck` + Vitest + `npm run build`.

## Dev Notes

### The audit table EXISTS — this corrects the roadmap note

Memory and the epics file both imply audit belongs to Epic 20 (backlog) and might block 18.5. The forensic sweep + direct schema read disprove this: `AuditEvent` is a real model ([db/models.py:291-318](src/ai_qa/db/models.py:291)) backed by the `audit_events` table (in `20260504_1201_initial_core_schema.py`), with `agent_run_id`/`project_id`/`user_id`/`event_type`/`resource_id`/`details` already present and relationships on `User`/`Project`/`AgentRun`. The ONLY missing piece is a service to write rows — there is no audit-writing code anywhere today. So 18.5 needs NO migration and has NO Epic-20 dependency; it just adds a thin writer. Epic 20 (20-3) later builds the admin VIEW over these rows. (Note: the `audit` dict passed to MCP tool calls — `{userPrompt, llmReasoning}` — is unrelated request metadata, not this audit trail.)

### `AuditEvent` has no `TimestampMixin` — set `created_at` explicitly

Unlike most models, `AuditEvent(UUIDPrimaryKeyMixin, Base)` does NOT inherit `TimestampMixin`; it declares a bare `created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)` ([db/models.py:314](src/ai_qa/db/models.py:314)) with no default. The service MUST set `created_at=datetime.now(UTC)` on insert or the NOT NULL constraint fails. (This is the one easy-to-miss footgun in this story.)

### Reuse the project-scoped broadcast filter — don't invent a new fan-out

`broadcast_artifact_change` ([api/websocket.py:488-533](src/ai_qa/api/websocket.py:488)) already iterates active connections and skips any whose `member_project_ids` doesn't include the changed project — exactly the privacy boundary 18.5 needs. Mirror it for `source_change`; do not broadcast project-internal drift to non-members.

### Current behavior to PRESERVE (regression guardrails)

- **All three legs best-effort (AC7).** Notice, broadcast, and audit each wrapped so one failing never aborts detection/cascade — match the existing best-effort publish at [api/artifacts.py:327-328](src/ai_qa/api/artifacts.py:327).
- **No-secret / no-content leak.** Audit `details`, notice text, and the realtime event carry only safe summary fields (ids, version numbers, hash PREFIXES, counts) — never raw page content or any credential ([[project-context]]).
- **English-only UI** ([[app-ui-english-only]]) for every notice + the FE drift indicator.
- **Full-stack sync.** New `SourceChangeEvent` ⇒ matching TS type in `frontend/src/types/` same change; `npm run build` ([[project-context]]).
- **Project-scoped delivery.** Realtime events only reach project members (reuse the existing filter) — no cross-project leakage.

### Source tree components to touch

- `src/ai_qa/audit/service.py` — **ADD** (`AuditService.record`).
- `src/ai_qa/models.py` — **ADD** (`SourceChangeEvent`).
- `src/ai_qa/api/websocket.py` — **UPDATE** (`broadcast_source_change`, mirror `broadcast_artifact_change`).
- `src/ai_qa/agents/bob.py` / detection + cascade flow (18.2/18.4) — **UPDATE** (post notices + call `AuditService` + broadcast).
- `frontend/src/App.tsx` + `frontend/src/types/` — **UPDATE** (drift-indicator branch + TS type).
- Tests — **ADD** for audit service, detection/cascade audit+broadcast, FE drift indicator.
- NO Alembic migration (uses the existing `audit_events` table).

### Decided scope (defaults — Thuong, correct if needed)

- **Write to the existing `audit_events` table** via a new thin `AuditService` — no migration, no Epic-20 dependency.
- **Notices only for `changed` sources + cascade decisions** (not for `unchanged`/`new`).
- **Realtime event = a new `source_change` type** reusing the project-member delivery filter; no admin audit-view UI (Epic 20).

### Testing standards summary

- Backend pytest; real `AuditEvent` rows in the test DB; assert `event_type`/`details` whitelist + tz-aware `created_at`. Best-effort isolation tests (force each leg to raise). Full-suite run.
- FastAPI deps via `app.dependency_overrides`; WS broadcast tested with stubbed `active_connections` member filter.
- No bare `pytest.raises(Exception)`; Pyrefly-clean optionals.

### Project Structure Notes

- Cross-cutting story — depends on 18.2 (detection) and 18.4 (cascade) for its trigger points. Can land the source-change leg (notice + broadcast + `source_change_detected` audit) with 18.2, and the cascade-decision audit with 18.4.
- No schema change; the one footgun is `AuditEvent.created_at` having no default.

### References

- Epic + story: [epics.md#Epic-18](_bmad-output/planning-artifacts/epics.md:2054), [Story 18.5](_bmad-output/planning-artifacts/epics.md:2086)
- Audit table (EXISTS): [db/models.py:291-318](src/ai_qa/db/models.py:291) (`AuditEvent`); created in `alembic/versions/20260504_1201_initial_core_schema.py`; relationships on `User`/`Project`/`AgentRun` ([threads/models.py:63-79](src/ai_qa/threads/models.py:63))
- Realtime broadcast: [api/websocket.py:488-533](src/ai_qa/api/websocket.py:488) (`broadcast_artifact_change`), [models.py:134-154](src/ai_qa/models.py:134) (`ArtifactChangeEvent`), [api/artifacts.py:327-328](src/ai_qa/api/artifacts.py:327) (best-effort publish)
- Messages: [models.py:74-132](src/ai_qa/models.py:74) (`AgentMessage`), [threads/service.py:308-314](src/ai_qa/threads/service.py:308) (system-message precedent)
- FE raw-event handler: [App.tsx:480-516](frontend/src/App.tsx:480)
- Depends on: [18-2 detection](_bmad-output/implementation-artifacts/18-2-source-change-detection-on-rerun.md), [18-4 cascade](_bmad-output/implementation-artifacts/18-4-guided-cascade-rerun-confirmation.md)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[message-timestamps-feature]], [[epic-10-artifact-ui-gotchas]], [[app-ui-english-only]], [[epic-roadmap-reprioritization-2026-06-20]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
