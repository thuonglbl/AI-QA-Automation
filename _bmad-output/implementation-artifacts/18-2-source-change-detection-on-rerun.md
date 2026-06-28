---
baseline_commit: 39bec831e2b195b3121a2345a32b282211bd9872
---
# Story 18.2: Source Change Detection vs Last Run

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend-led (small FE notice). Builds directly on 18.1. When Bob re-consumes a Confluence page / Jira issue, it reads the **most recent prior `SourceSnapshot`** for that `(project_id, source_type, source_id)` (written by an earlier run) and compares the freshly fetched content against it. The result — `unchanged` / `changed` / `new` per source — is **reported to the user BEFORE any regeneration**, as a chat notice + a `source_change_report` metadata payload. **Detection only**: this story does NOT map downstream staleness (18.3) or cascade-regenerate (18.4). Detection is **on-demand** (no scheduler exists in this codebase): it runs at the start of a Bob extraction run, plus via an explicit "Check for source changes" action.

## Story

As a QA user,
I want Bob to detect whether the bound Confluence/Jira sources changed since the last snapshot,
so that I am told what changed before regenerating anything.

## Acceptance Criteria

1. **Compare current fetch against the latest prior snapshot.** Given a source Bob is consuming and a prior `SourceSnapshot` exists for the same `(project_id, source_type, source_id)` from an EARLIER run, when Bob processes it, then it computes the current `content_hash` (identical algorithm/serialization to 18.1) and the current `source_version`, looks up the latest prior snapshot via `SourceSnapshotService.latest_for_source(..., before_run_id=current_run_id)`, and classifies the source as: `unchanged` (current hash == prior hash), or `changed` (hash differs). The cheap `source_version` (Confluence version int / Jira `updated`) is checked first as a fast-path but the **hash is authoritative** — a version bump with identical content is `unchanged`; a hash difference with an unchanged version is still `changed` (and logged as a version-tracking anomaly).

2. **Absent prior snapshot ⇒ `new`, never a false `changed`.** Given a source with NO prior snapshot row (a brand-new source, or one created before Epic 18 shipped — see 18.1 AC7), when Bob processes it, then it is classified `new` / `baseline-established`, NOT `changed`. The current run's snapshot still gets written (by 18.1) so the NEXT run has a baseline. This guarantees the very first detection after rollout never floods the user with phantom changes.

3. **Per-source change report, surfaced before regeneration.** Given a run that has compared all its sources, when detection finishes, then Bob emits a structured `source_change_report` — a chat message (`sender="agent"`, an `info`/`warning` message) carrying `metadata={"type": "source_change_report", "sources": [{source_type, source_id, source_url, title, status, prior_version, current_version, prior_hash_prefix, current_hash_prefix, last_checked_at}], "changed_count": N, "new_count": M, "unchanged_count": K}`. Hash values are surfaced as short prefixes (e.g. first 12 chars) for display, never the raw content. The summary line is human-readable English (App-UI-English-only, [[app-ui-english-only]]), e.g. `"2 of 3 sources changed since the last run."`.

4. **On-demand "Check for source changes" action.** Given a thread that has prior snapshots for its bound sources, when the user triggers a "Check for source changes" action, then Bob re-fetches the bound sources, runs detection (AC1/AC2), emits the `source_change_report` (AC3), and does NOT regenerate requirements. This is a lightweight read-only check — it fetches sources and compares, then stops. **Transport note (verified):** the WS receive loop routes ONLY `start`/`approve`/`reject`/`navigate` ([api/websocket.py:186](src/ai_qa/api/websocket.py:186); `_dispatch_action` calls only `handle_start`/`handle_approve`/`handle_reject` at [api/websocket.py:368-377](src/ai_qa/api/websocket.py:368)) — there is NO generic custom-action type. So this action must ride the existing `approve` channel as a `data` payload and be routed inside Bob's `handle_approve` ([bob.py:1879](src/ai_qa/agents/bob.py:1879)) — exactly how `clarify_answer` works: `handle_approve` dispatches by `self.phase` ([bob.py:1985](src/ai_qa/agents/bob.py:1985) → `_handle_clarify_answer`), and `_handle_clarify_answer` sub-routes on `data["action"]` ([bob.py:1698-1711](src/ai_qa/agents/bob.py:1698)). Do NOT add a new top-level WS message type.

5. **Detection runs before the new snapshot is written.** Given a run writes a new snapshot per 18.1, when both detection and snapshot-write happen in the same run, then detection reads the PRIOR snapshot first (using `before_run_id=current_run_id`, or by reading before the new row is inserted) so the run never diffs its own freshly written snapshot against itself (which would always read `unchanged`). Ordering: fetch → detect (read prior) → persist (write new).

6. **Detection never aborts extraction; missing baseline degrades gracefully.** Given any failure in the comparison (DB read error, malformed prior row), when it occurs, then it is logged (safe fields) and that source is reported with status `unknown` (or `new`), and extraction proceeds normally. Detection is advisory — it MUST NOT block or break requirement extraction (best-effort contract, [[ws-nonblocking-clarify-timeout-fix]]).

7. **Frontend renders the change report unobtrusively.** Given the FE receives a message with `metadata.type === "source_change_report"`, when it renders, then it shows a compact, dismissible notice listing each source with a status chip (Changed / New / Unchanged) and the last-checked time, following the existing metadata-driven render pattern in [App.tsx:826-1080](frontend/src/App.tsx:826) (e.g. how `clarify_request` / `script_validation_error` render). No blocking modal; no action required from the user in THIS story (the cascade prompt is 18.4). All strings English.

## Tasks / Subtasks

- [ ] **Task 1 — Detection logic (AC: 1, 2, 5, 6)**
  - [ ] Add a `detect_source_change(*, project_id, source_type, source_id, current_content, current_version, current_run_id) -> SourceChangeStatus` to the snapshot service (or a thin `SourceChangeDetector` beside it). It computes the current hash, calls `latest_for_source(..., before_run_id=current_run_id)`, and returns a small dataclass/Pydantic `SourceChangeStatus { status: Literal["unchanged","changed","new","unknown"], prior_version, current_version, prior_hash, current_hash, last_checked_at }`.
  - [ ] Version fast-path then hash authority (AC1): if `prior` is None → `new`; elif `prior.content_hash == current_hash` → `unchanged`; else → `changed`. Log a warning if `source_version` is unchanged but the hash differs (anomaly worth surfacing in retro).
  - [ ] Wrap in `try/except → logger.warning → status="unknown"` (AC6).

- [ ] **Task 2 — Wire detection into Bob's run + emit the report (AC: 1, 3, 5)**
  - [ ] In Bob's retrieval flow, for each consumed source, run `detect_source_change(...)` BEFORE 18.1's `record_snapshot(...)` writes the new row (AC5). Collect per-source statuses into a list.
  - [ ] Confluence: detect at the Phase-1 seam where the `ConfluencePage` is in hand ([bob.py:1044-1048](src/ai_qa/agents/bob.py:1044)) — current_content = `page.content`, current_version = `page.version`. Jira: detect in `_retrieve_jira_requirements` ([bob.py:497-554](src/ai_qa/agents/bob.py:497)) — current_content = the same deterministic serialization 18.1 hashes, current_version = `issue.updated_at`.
  - [ ] After all sources are processed, build + `send_message(...)` the `source_change_report` (AC3) with the per-source list and the counts. Keep the summary concise; the report is advisory only.

- [ ] **Task 3 — "Check for source changes" action (AC: 4)**
  - [ ] Carry the action over the EXISTING `approve` channel (no new WS message type): FE sends `{type:"approve", step:1, data:{action:"check_source_changes"}}`. Add a branch in Bob's `handle_approve` ([bob.py:1879](src/ai_qa/agents/bob.py:1879)) that detects `data.get("action") == "check_source_changes"` and dispatches to a new `_handle_check_source_changes`, mirroring how `handle_approve` routes `clarify` by phase ([bob.py:1985](src/ai_qa/agents/bob.py:1985)) and `_handle_clarify_answer` sub-routes on `data["action"]` ([bob.py:1698-1711](src/ai_qa/agents/bob.py:1698)). Do NOT extend the WS action router (`_dispatch_action`/`_handle_action`, [api/websocket.py:368-377](src/ai_qa/api/websocket.py:368)) with a new type — it only knows start/approve/reject.
  - [ ] The handler re-fetches the thread's bound sources (reuse the existing reader path), runs detection, emits the report, and returns WITHOUT regenerating (read-only). It runs under the per-agent action lock automatically (the `approve` dispatch already acquires it, [api/websocket.py:360](src/ai_qa/api/websocket.py:360)), so it won't interleave with an in-flight extraction ([[ws-nonblocking-clarify-timeout-fix]]).

- [ ] **Task 4 — `SourceChangeReport` payload model (AC: 3)**
  - [ ] Define the report payload (Pydantic, in `src/ai_qa/models.py` near `ArtifactChangeEvent` at [models.py:134-154](src/ai_qa/models.py:134), or in the snapshot module) with the fields in AC3. Surface only hash PREFIXES, not full content. Keep it serializable for the WS metadata.

- [ ] **Task 5 — Frontend notice (AC: 7)**
  - [ ] Add a render branch for `metadata.type === "source_change_report"` in [App.tsx](frontend/src/App.tsx) following the existing metadata-routing switch ([App.tsx:826-1080](frontend/src/App.tsx:826)). Render a compact list with per-source status chips (Changed/New/Unchanged) + last-checked time. Dismissible; no action buttons (cascade is 18.4). Add the TS type for the payload in `frontend/src/types/` to keep full-stack sync ([[project-context]] full-stack-sync rule); `npm run typecheck` + `npm run build`.

- [ ] **Task 6 — Tests (all ACs)**
  - [ ] Detector unit: prior==current → `unchanged`; prior!=current → `changed`; no prior → `new`; DB error → `unknown` (no raise). Version-unchanged-but-hash-changed logs the anomaly and returns `changed`.
  - [ ] Bob integration: stub reader returns the SAME page twice across two runs (run 1 establishes baseline → all `new`; run 2 identical → all `unchanged`); then mutate `page.content` for run 3 → that source `changed`. Assert the emitted `source_change_report` counts + per-source statuses. Detection reads the run-1/run-2 snapshot, not its own (AC5).
  - [ ] Action handler: "check for source changes" emits a report and does NOT call `save_requirement_page`/regeneration; respects the agent lock.
  - [ ] Frontend: Vitest render of the `source_change_report` branch (status chips, English strings, dismiss). Mock the message; `npm run typecheck`.
  - [ ] `uv run pytest` (full suite) + ruff + `mypy src`; `npm run typecheck` + relevant Vitest.

## Dev Notes

### This story is "read the prior snapshot and compare" — nothing more

18.1 writes the baseline; 18.2 reads it. The whole story hinges on `SourceSnapshotService.latest_for_source(...)` returning the previous run's row and a hash comparison. Resist scope creep: do NOT walk lineage (that's 18.3) and do NOT prompt for or trigger regeneration (that's 18.4). The deliverable is an honest, advisory "here's what changed" report.

### Why hash authority over version (AC1)

Confluence bumps `version` on trivial edits (a label change, a re-publish) that may not change the requirement-bearing body; and a restore can REUSE an old version number. Jira's `updated` moves on comments and field touches unrelated to the spec. So `source_version` is a cheap pre-filter for the UI ("v4 → v7") but the SHA-256 of the source content is what actually decides `changed` vs `unchanged`. Keep both; let the hash win.

### The "first run after rollout" trap (AC2)

The single most likely bug: every existing project has artifacts but NO snapshots, so a naive "no match ⇒ changed" would tell every user "everything changed" on first check. AC2 forbids this — absent prior snapshot is `new`/baseline, full stop. The first run silently establishes baselines; meaningful change detection starts on the SECOND run.

### Current behavior to PRESERVE (regression guardrails)

- **Advisory, non-blocking.** Detection appends a report; it never gates extraction, never changes `self.pages`, never blocks the run ([[ws-nonblocking-clarify-timeout-fix]]). Best-effort everywhere (AC6).
- **Order matters (AC5) — and detection must run INLINE.** Detect (read prior) strictly before 18.1's snapshot write, else the run diffs against itself. `await detect_source_change(...)` inline in the retrieval loop (~[bob.py:1048](src/ai_qa/agents/bob.py:1048)) — do NOT spawn it as a background `asyncio.create_task`, or it can race the snapshot write and violate the fetch→detect→write ordering. (The on-demand `approve`-channel action IS already dispatched as a background task by the WS loop at [api/websocket.py:191](src/ai_qa/api/websocket.py:191), which is fine — that is the action wrapper, not the detect-vs-write ordering inside it.) If 18.1 and 18.2 land together, enforce ordering in one place.
- **Agent action lock.** The on-demand action runs through the same per-agent serialization lock as start/approve/reject so it can't interleave with a live extraction ([api/websocket.py:360](src/ai_qa/api/websocket.py:360)).
- **English-only UI + no-secret-leak.** All report strings English ([[app-ui-english-only]]); surface hash prefixes, never raw content or credentials ([[project-context]]).
- **Full-stack sync.** New WS metadata payload ⇒ matching TS interface in `frontend/src/types/` in the SAME change; `npm run build` to verify ([[project-context]]).

### Source tree components to touch

- `src/ai_qa/sources/snapshot_service.py` (from 18.1) — **UPDATE** (add `detect_source_change` / `latest_for_source` use).
- `src/ai_qa/models.py` — **ADD** (`SourceChangeReport`/`SourceChangeStatus` payload models).
- `src/ai_qa/agents/bob.py` — **UPDATE** (run detection in the retrieval loops; emit the report; add the `_handle_check_source_changes` action).
- `src/ai_qa/api/websocket.py` — **UPDATE if needed** (route the new "check_source_changes" action, mirroring `clarify_answer`).
- `frontend/src/App.tsx` + `frontend/src/types/` — **UPDATE** (render `source_change_report`; add the TS type).
- Tests — **ADD** for detector, Bob integration, action handler, and FE render.

### Decided scope (defaults — Thuong, correct if needed)

- **On-demand only** (no scheduler in this codebase): detection runs at run-start AND via an explicit user action. Scheduled/polling detection is explicitly OUT of scope.
- **Hash is authoritative**, version is a display/fast-path hint.
- **Report is advisory** — no cascade prompt, no staleness map, no regeneration in this story.

### Testing standards summary

- Backend pytest; mock the reader (return controllable `ConfluencePage`/`JiraIssue`), use the real DB models + snapshot rows. Full-suite run for the coverage gate.
- No bare `pytest.raises(Exception)`; Pyrefly-clean optionals on `PipelineContext` + mock `call_args`.
- Frontend Vitest: prefer fetch-spy / `importOriginal()` over file-wide `vi.mock` ([[project-context]]).

### Project Structure Notes

- No Alembic migration in this story (reads 18.1's table; adds only Pydantic payloads + a render branch).
- Depends on 18.1 (`SourceSnapshot` + service). If implementing before 18.1 is merged, stub `latest_for_source` against the new table.

### References

- Epic + story: [epics.md#Epic-18](_bmad-output/planning-artifacts/epics.md:2054), [Story 18.2](_bmad-output/planning-artifacts/epics.md:2068)
- Foundation: [18-1-source-snapshot-persistence.md](_bmad-output/implementation-artifacts/18-1-source-snapshot-persistence.md)
- Bob detection seams: [bob.py:1044-1048](src/ai_qa/agents/bob.py:1044) (Confluence), [bob.py:497-554](src/ai_qa/agents/bob.py:497) (Jira), [bob.py:1698-1727](src/ai_qa/agents/bob.py:1698) (`clarify_answer` action precedent)
- WS action dispatch: [api/websocket.py:315-388](src/ai_qa/api/websocket.py:315) (`_handle_action`), [api/websocket.py:360](src/ai_qa/api/websocket.py:360) (per-agent lock)
- FE metadata routing: [App.tsx:826-1080](frontend/src/App.tsx:826)
- Payload precedent: [models.py:134-154](src/ai_qa/models.py:134) (`ArtifactChangeEvent`), `AgentMessage` [models.py:74-132](src/ai_qa/models.py:74)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[ws-nonblocking-clarify-timeout-fix]], [[bob-clarify-loop]], [[app-ui-english-only]], [[message-timestamps-feature]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
