---
title: 'Bob requirements extraction — Continue/resume after interruption'
type: 'feature'
created: '2026-06-23'
status: 'done'
baseline_commit: '0888bb9e89493c798a6b492e7e310691d2f4223e'
context:
  - '{project-root}/project-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/investigations/bob-parse-resume-on-interrupt-investigation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** When a Bob Confluence extraction is interrupted mid-batch (server restart / process death), `reconcile_interrupted_work` resets the thread to `start` and re-submitting re-runs the whole extract+convert batch from scratch — every already-converted page is re-fetched and re-converted by the LLM, wasting minutes on slow on-prem models. No resume affordance exists.

**Approach:** (1) `_extract_descendants` **reuses** any page whose requirement `.md` is already saved instead of re-converting (universal skip — every run, not just resume). (2) Persist the confirmed parent on the thread so a resume replays it with no re-entry. (3) On reconcile, flag the system message with `resume_available` when the stuck thread had a persisted Bob parent. (4) A "Continue" button on that message fires a resume `start` action; `handle_start`'s resume branch replays extraction from the persisted parent, skipping saved pages.

## Boundaries & Constraints

**Always:**
- Reuse existing machinery: `adapter.load_requirement_markdown()` (saved set), the `handle_approve` confirm_parent post-extraction flow (auto-save + select-id) for resume, the `is_confirm_parent` metadata→button pattern (FE).
- A reused page still appears in `self.pages` (hydrated from saved `.md`); only the LLM `convert_markdown` call is skipped. Resume requires no re-entry of URL/parent/MCP key (secret already stored).
- Quality gates per `project-context.md`: nullable column + Alembic migration, `mypy src` clean, Ruff check+format, async LLM via `ainvoke`, no secrets in logs/messages.

**Ask First:** Any change to the existing "skip" path (blank URL → hand off to Mary) or to `reconcile_interrupted_work` for non-Bob threads.

**Never:**
- No separate "force re-extract" path — refresh changed content by deleting the artifact (user decision: "always skip").
- No new WS msg_type / dispatcher change — resume rides `type:"start"` + `inputData.resume=true`. No Thread API/TS-type expansion — the signal rides the persisted Message metadata.
- Do not regress per-page convert-failure tolerance (stub + continue) or the empty-page anti-hallucination guard.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Resume after interrupt | Thread reset to `start`, `bob_resume_parent` set, some pages already have `.md` | Reconcile message shows "Continue"; click replays extraction from the persisted parent, reuses saved `.md` (no LLM convert), converts only the remaining pages, auto-saves, hands off to select-id | Persisted parent unresolvable → surface an error message, stay at `start` (intake form still usable) |
| Universal skip on any run | Extraction runs; some pages already saved for the project | Saved pages reused without `convert_markdown`; only un-saved pages converted | Per-page convert failure still stubbed + loop continues (unchanged) |
| Completed run | Extraction finished, `bob_resume_parent` cleared | No "Continue" button appears | N/A |
| Resume, nothing saved yet | `bob_resume_parent` set but zero saved `.md` | Replays the full batch normally (nothing to skip) | N/A |

</frozen-after-approval>

## Code Map

- `src/ai_qa/threads/models.py` -- add `Thread.bob_resume_parent: Mapped[str | None]` (nullable `String(512)`), the confirmed-parent string to replay.
- `alembic/versions/<new>_add_bob_resume_parent.py` -- migration adding the nullable column (chain off current head).
- `src/ai_qa/agents/bob.py` -- (a) `_extract_descendants` (906): load saved page-id→content once before the loop; skip `read_page_by_id` + `convert_markdown` for saved pages and hydrate `self.pages` from saved `.md` (raw_html may be empty for reused pages — `process()` already tolerates that, bob.py:697). (b) `handle_approve` confirm_parent branch (1921-1969): persist `confirmed_page` → `thread.bob_resume_parent` before `_extract_descendants`; clear it (`None`) after `_auto_save_requirements` succeeds. (c) `handle_start` (556): if `input_data.get("resume")`, after preconditions read `thread.bob_resume_parent`, set `self.phase="confirm_parent"`, and `await self.handle_approve({"confirmed_page_name": parent})`; return (no URL validation).
- `src/ai_qa/threads/service.py` -- `reconcile_interrupted_work` (264): when a reset thread has `bob_resume_parent` set, attach `message_metadata={"resume_available": True}` to the system Message it already creates.
- `frontend/src/App.tsx` -- render a "Continue" button on any message with `metadata.resume_available` (gate: `isBobStep && status === "start"`), sending `sendMessage({ type: "start", step: 2, inputData: { resume: true } })`. Mirror the `is_confirm_parent` rendering/handler pattern.
- `tests/unit/test_bob_agent*.py` + `tests/unit/test_threads_service.py` -- new coverage (below).

## Tasks & Acceptance

**Execution:**
- [x] `src/ai_qa/threads/models.py` -- add nullable `bob_resume_parent` column.
- [x] `alembic/versions/f1a2b3c4d5e6_add_bob_resume_parent_to_threads.py` -- migration for the column (chains off `d9c4f1a6e2b8`; confirmed single linear head via `alembic heads`).
- [x] `src/ai_qa/agents/bob.py` -- universal skip-and-reuse in `_extract_descendants`; persist/clear parent in `handle_approve`; resume branch + `_handle_resume`/`_set_resume_parent`/`_get_resume_parent` helpers in `handle_start`.
- [x] `src/ai_qa/threads/service.py` -- set `resume_available` metadata on the reconcile message for threads with a persisted parent.
- [x] `frontend/src/App.tsx` -- "Continue" button (gated `isBobStep && status==="start" && resume_available`) wired to the resume `start` action via `handleBobContinue`.
- [x] tests -- backend: (1) page whose `.md` exists → `convert_markdown` NOT called, no raw re-fetch, saved content reused; (2) `reconcile_interrupted_work` sets `resume_available` only when `bob_resume_parent` is present. FE: Continue button renders on a `resume_available` message and sends `start`+`resume`.

**Acceptance Criteria** (system-level; I/O scenarios above are not repeated):
- Given the "Continue" button, when clicked, then a `start` action with `inputData.resume=true` is sent and Bob replays from the persisted parent with no re-entry of URL/parent/MCP key.
- Given a page whose requirement `.md` exists, when `_extract_descendants` runs, then `convert_markdown` is not called for it and its saved content is reused in `self.pages`.
- Given extraction completes successfully, then `bob_resume_parent` is cleared (so the button no longer appears); `reconcile_interrupted_work` sets `resume_available` only when the column is set.

## Design Notes

The resume branch only sets `phase="confirm_parent"` and calls `handle_approve({"confirmed_page_name": <parent>})`, so auto-save / clarify / select-id run unchanged. The persisted-parent column doubles as the interrupted-vs-completed signal (set before extraction, cleared on success), letting the reconcile message flag resume without inspecting artifacts.

## Verification

- `uv run alembic upgrade head` (then `downgrade -1` → `upgrade head` round-trips); `uv run ruff check --fix src/ tests/` && `uv run ruff format src/ tests/`; `uv run mypy src` -- all clean.
- `uv run pytest tests/unit/test_bob_agent_extraction.py tests/unit/test_threads_service.py --no-cov` -- new tests pass (`--no-cov` per coverage-gate note; add `-p no:base_url` if needed).
- `cd frontend && npm run typecheck` + the App vitest covering the Continue button -- clean.
- Manual: start a multi-page run, restart backend mid-`Parsing`, reload → "Continue" appears; click resumes, saved pages reused (no LLM wait), only remaining pages convert.

## Suggested Review Order

**Reuse core (start here — the design intent)**

- Entry point: load already-saved pages, then skip both re-fetch and LLM convert for them.
  [`bob.py:1097`](../../src/ai_qa/agents/bob.py#L1097)
- Precedence fix: the approved `{pid}/requirement.md` wins over the per-page draft `{pid}.md`.
  [`bob.py:1097`](../../src/ai_qa/agents/bob.py#L1097)
- Phase-2 reset removed (moved to Phase 1) so reused pages aren't wiped before conversion.
  [`bob.py:1092`](../../src/ai_qa/agents/bob.py#L1092)

**Resume entry & parent lifecycle**

- Resume branch: a `start` action with `inputData.resume=true` short-circuits the intake.
  [`bob.py:637`](../../src/ai_qa/agents/bob.py#L637)
- `_handle_resume`: replays via `handle_approve`; pre-resolves page/space (title-only fallback).
  [`bob.py:207`](../../src/ai_qa/agents/bob.py#L207)
- Persist parent before extraction; clear it on successful completion (the resumable signal).
  [`bob.py:2052`](../../src/ai_qa/agents/bob.py#L2052)
- Persistence helpers (best-effort, never break extraction).
  [`bob.py:179`](../../src/ai_qa/agents/bob.py#L179)

**Schema**

- New nullable column carrying the confirmed parent.
  [`models.py:40`](../../src/ai_qa/threads/models.py#L40)
- Additive migration, chained off head `d9c4f1a6e2b8`.
  [`f1a2b3c4d5e6:25`](../../alembic/versions/f1a2b3c4d5e6_add_bob_resume_parent_to_threads.py#L25)

**Interrupt signal**

- Reconcile flags the persisted system message with `resume_available` for resumable threads.
  [`service.py:308`](../../src/ai_qa/threads/service.py#L308)

**UI binding**

- "Continue" button gated on `isBobStep && status==="start" && resume_available`.
  [`App.tsx:2365`](../../frontend/src/App.tsx#L2365)
- Handler sends the resume `start` action — no URL/parent/MCP re-entry.
  [`App.tsx:1561`](../../frontend/src/App.tsx#L1561)

**Tests**

- Reuse skips `convert_markdown` + raw re-fetch; saved content carried into `self.pages`.
  [`test_bob.py:1085`](../../tests/test_agents/test_bob.py#L1085)
- Approved copy preferred over a stale draft (draft listed first).
  [`test_bob.py:1157`](../../tests/test_agents/test_bob.py#L1157)
- Reconcile sets `resume_available` only when a parent is persisted.
  [`test_threads_service.py:196`](../../tests/unit/test_threads_service.py#L196)
- Continue button renders on a `resume_available` message and sends `start`+`resume`.
  [`App.test.tsx:574`](../../frontend/src/App.test.tsx#L574)
