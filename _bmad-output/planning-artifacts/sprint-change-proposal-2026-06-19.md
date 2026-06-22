# Sprint Change Proposal: Bob Requirements Chat UX + Interactive Clarification Loop

Date: 2026-06-19
Author: Developer (correct-course)
Epic context: Epic 11 (Bob — Requirements extraction) — UX refinement, no structural epic change.

## 1. Issue Summary

- **Triggering issue**: Running the Bob — Requirements step end-to-end against the "PTP Personal Travel Plan" project surfaced five UX/flow problems, the most important being that Bob's quality check is **advisory-only** — it warns about unclear requirements but takes no action, leaving low-quality MD files to flow downstream to Mary.
- **Context**: Epic 11 is `done`, but real-world use exposed friction the story ACs did not cover. These are refinements within the existing Bob flow, not a re-plan.
- **Evidence**: Two screenshots of the live UI (chat force-scrolls down while reading; a redundant "Saved 7 requirements…" bubble duplicating the inline "Requirements saved…" prompt; a "Quality issues detected…" warning with no follow-up action; the "Bob's thought / Extract from MCP: done" status block rendering out of order; a stray input placeholder).

## 2. Impact Analysis

- **Epic impact**: Epic 11 only. No new/removed/reordered epics. No change to Epics 12–13 (Mary/Sarah) — they consume the same approved `requirement.md` artifacts; clarification only **improves** their input quality.
- **PRD / Architecture impact**: None. The clarification loop reuses the existing Bob phase/state machine, the existing `_detect_quality_issues` deterministic scan, the thread provider's LLM, and the idempotent artifact-save path. No schema/migration change.
- **Artifact (requirement.md) impact**: The clarification loop **overwrites** the approved `requirement.md` via the existing idempotent `PipelineArtifactAdapter.save_requirement` (save-new-first, delete-superseded) — same write path used at auto-save, so no new storage contract.
- **Technical impact** (files, all verified):
  - Backend — `src/ai_qa/agents/bob.py`: reorder two `send_message` calls (point 2); add a new `clarify` phase + handlers + LLM helpers (point 5).
  - Frontend — `frontend/src/App.tsx`: scroll effect + floating button (point 1); filter rule for `is_select_id` (point 3); remove placeholder (point 4); new clarify panel + message handler (point 5). Reference pattern for point 1 already exists in `frontend/src/components/ChatArea.tsx` (currently unused).
- **Full-stack sync**: A new `clarify_request` message + its metadata must be added to the FE message handling; if a typed field is added, update the `AgentMessage`/metadata typing in `frontend/src/types/pipeline.ts`.

## 3. Recommended Approach

- **Path forward**: Direct Adjustment (Option 1). Refine Bob + the chat UI in place.
- **Rationale**: Self-contained within Epic 11; no MVP/goal change; turns a known weak spot (advisory-only quality check — the open risk in the Epic 11 retro) into an active, requirement-improving loop without altering downstream contracts.
- **Effort**: Points 1–4 Low; Point 5 Medium. **Risk**: Low–Medium (point 5 adds an LLM round-trip per answer and a new interactive phase — mitigated by a max-rounds guard + per-item Skip).

### Locked design decisions (confirmed by Thuong)

1. **Clarification = Hybrid LLM.** Deterministic `_detect_quality_issues` decides *which* files/points are unclear; the thread LLM *phrases* the question per file and *rewrites* the MD from the user's answer.
2. **Per-item escape hatch.** Each unclear point can be Skipped/acknowledged; a per-file max-round guard prevents infinite loops. The select-id prompt only appears once every point is **cleared or skipped**.
3. **Ship all five points together**, then one review pass.

## 4. Detailed Change Proposals

### Point 1 — Persist scroll position + floating "New message" button (FE)

`frontend/src/App.tsx:626-642` currently force-scrolls on every new message and unconditionally resets `userScrolledUpRef.current = false`.

```text
WAS: on new message → reset userScrolledUpRef=false → scrollIntoView (always)
NEW: on new message →
       if user is scrolled up  → setHasNewMessage(true)   // do NOT scroll
       else                     → scrollIntoView + clear hasNewMessage
     on scroll back to bottom (handleChatScroll) → clear hasNewMessage
```

- Add `hasNewMessage` state; render a floating pill button (reuse `ChatArea.tsx:91-100` markup — `lucide-react` `ArrowDown` + "New message", absolute-positioned over the chat container) shown only while `userScrolledUp && hasNewMessage`; click → scroll to `chatBottomRef` and clear.
- Keep the streaming-update branch (`!userScrolledUpRef.current`) behavior. Keep the thread-switch reset (`App.tsx:657`).

### Point 2 — Show "Extract from MCP: done" before the quality message (BE + FE)

`src/ai_qa/agents/bob.py`: in `_extract_descendants`, the `thinking_trace` ("Connect status: OK / Extract requirements from MCP: done") is emitted at `bob.py:1181` **after** `_run_quality_detection()` at `bob.py:1179`. **Swap** so the order becomes: per-page `✓ Converted '…'` → thinking_trace block → quality summary.

```text
NEW order in _extract_descendants tail:
  1) send_message(thinking_trace: ["Connect status: OK", "Extract requirements from MCP: done"])
  2) self._has_quality_warnings = await self._run_quality_detection()   # emits the summary AFTER the trace
```

- FE: verify the `thinking_trace` block (filtered at `App.tsx:1776`, rendered via the ThinkingBubble) appears **inline at its chronological position** (right after the last "Converted" bubble, before the quality summary). If it currently renders in a fixed slot, render it inline at its message timestamp instead.

### Point 3 — Remove the redundant "Saved N requirements…" bubble (FE)

`bob.py:1463-1470` emits a `text` bubble ("Saved N requirements from Confluence. Please input…") carrying `metadata.is_select_id`. The FE filter (`App.tsx:1748`) does **not** hide it, so it renders as a bubble **in addition to** the inline select-id prompt text ("Requirements saved. Please input…", `App.tsx:1983`).

```diff
  // in the .filter() at App.tsx:1748, alongside the other metadata-driven hides
+ // is_select_id only drives the inline select-id input; never a chat bubble
+ if (msg.metadata?.is_select_id) return false;
```

- Keep the backend message (the `is_select_id` metadata still triggers `selectIdPrompt`); only its bubble is hidden. The inline prompt's own text remains the single source.

### Point 4 — Remove the input placeholder (FE)

`frontend/src/App.tsx:1994` — drop `placeholder="e.g. TOOL-1635"` (empty placeholder).

### Point 5 — Interactive clarification loop (BE + FE) — the core change

**Goal**: After auto-save, if any requirement has *blocking* unclear points, Bob runs a back-and-forth: asks a file-specific question → user answers (or Skips) → LLM rewrites that `requirement.md` → re-scans → repeats until the file is clear or all points skipped → moves to the next file → only when the queue is empty does the select-id prompt appear.

**Backend — `src/ai_qa/agents/bob.py`**

- New phase value `"clarify"` (between auto-save and `"select_id"`).
- New constants:
  - `_BLOCKING_QUALITY_CATEGORIES = {"missing_preconditions", "missing_expected_results", "insufficient_content"}` — these gate progression.
  - Advisory categories (`vague_language`, `ambiguous_ui_reference`, `unsupported_content`) are surfaced inside the question but are **non-blocking** (informational; cleared by Skip if untouched).
  - `_MAX_CLARIFY_ROUNDS = 3` per page.
- New per-run state: `_clarify_queue: list[str]` (page_ids), `_clarify_rounds: dict[str, int]`, `_clarify_done: set[str]`.
- `handle_approve` (confirm_parent phase): after `_auto_save_requirements()`, call `await self._begin_clarification_or_select()` **instead of** going straight to `select_id`.
- New methods:
  - `_begin_clarification_or_select()` — build queue of pages whose stored `quality_issues` intersect `_BLOCKING_QUALITY_CATEGORIES`. Empty → `_prompt_select_id()`. Else → phase `"clarify"`, `REVIEW_REQUEST`, `await self._ask_clarification(queue[0])`.
  - `_compose_clarify_question(page)` — LLM call: given the MD + the unclear points, produce a short, specific question (e.g. "US02 - Journey list: chưa nêu preconditions — người dùng đã đăng nhập chưa? cần seed data gì? …"). Falls back to a templated question if the LLM call fails.
  - `_ask_clarification(page_id)` — emit `message_type="text"`, `metadata={type:"clarify_request", page_id, page_title, source_url, points:[{category, message}]}`.
  - `_handle_clarify_answer(data)` — routed from `handle_approve` while phase `"clarify"`. Branches on `data.action`:
    - `skip_file` → mark `_clarify_done.add(page_id)` → advance.
    - `clarify_answer` → `_apply_clarification(page, answer)` (LLM rewrites MD), overwrite via `adapter.save_requirement(...)`, re-run `_detect_quality_issues`, refresh `page["quality_issues"]`, `_clarify_rounds[page_id] += 1`. If still-blocking **and** rounds `< _MAX_CLARIFY_ROUNDS` → re-ask same page; else advance (clean or maxed-out).
    - On advance: pop queue; if more pages → `_ask_clarification(next)`; else → `_prompt_select_id()`.
  - `_apply_clarification(page, answer)` — LLM call: rewrite the requirement MD incorporating the answer (e.g. add a `## Preconditions` / `## Acceptance Criteria` section), preserving the embedded `**Source:**` link.
  - `_prompt_select_id()` — extract the existing emit from `handle_approve` (the `is_select_id` message); reused at both the "no issues" and "all cleared/skipped" exits.
- Routing: extend `handle_approve` so `self.phase == "clarify"` dispatches to `_handle_clarify_answer(data)` (mirrors how `select_id`/`confirm_parent` already reuse `approve` + `data`).
- Repurpose the `_run_quality_detection` summary's trailing line ("You can still approve to proceed…") into a lead-in to the clarify session (the warning now precedes an action, not a dead end).

**Frontend — `frontend/src/App.tsx`**

- `bobState`: add `clarifyPrompt: boolean` + `clarifyData: { pageId, pageTitle, sourceUrl, points, question } | null` + `clarifyInput: string`.
- `handleBobMessage`: on `metadata.type === "clarify_request"` → set `clarifyPrompt=true` + `clarifyData`. When `is_select_id` arrives, clear `clarifyPrompt` (existing `selectIdPrompt` path takes over).
- New inline clarify panel (sibling of the select-id block at `App.tsx:1976`): shows the question + bulleted unclear points, a `<textarea>` reply, and buttons **"Gửi câu trả lời"**, **"Bỏ qua điểm này"** (skip current question/round), **"Bỏ qua file này"**.
- `handleBobClarifyAnswer(action, answer)` — send WS `{type:"approve", data:{action, page_id, answer}}` (reuse the existing approve channel, like `handleBobSelectId`).
- Add `clarify_request` to the filter hide-list (`App.tsx:1748`) so the carrier text isn't double-rendered.
- Types: if a typed clarify payload is introduced, mirror it in `frontend/src/types/pipeline.ts`.

## 5. Implementation Handoff

- **Scope**: Points 1–4 = Minor; Point 5 = Moderate. Combined → **Moderate**.
- **Assigned to**: Developer agent (this session), all five together.
- **Out of scope / deferred**: tuning the LLM prompts for question phrasing and MD rewrite quality is part of point 5 but may need a follow-up pass after live testing (ties into the Epic 11 extraction-quality risk).
- **Action items**:
  1. `bob.py` — reorder thinking_trace vs quality summary (point 2).
  2. `bob.py` — add `clarify` phase: state, constants, `_begin_clarification_or_select`, `_compose_clarify_question`, `_ask_clarification`, `_handle_clarify_answer`, `_apply_clarification`, `_prompt_select_id`; route via `handle_approve` (point 5).
  3. `App.tsx` — scroll persistence + floating "New message" button (point 1).
  4. `App.tsx` — hide `is_select_id` bubble (point 3); remove placeholder (point 4).
  5. `App.tsx` — clarify panel + `handleBobClarifyAnswer` + `handleBobMessage` branch + filter hide for `clarify_request` (point 5); FE type sync if needed.
  6. Tests: backend unit tests for the clarify state machine (queue build, blocking vs advisory, skip paths, max-round exit, select-id only after queue empty) — SQLite/no-cov per project test rules; FE behavior covered manually + existing scroll tests.
- **Verification**: `uv run ruff check --fix` + `uv run ruff format` + `mypy src` + `uv run pytest`; `npm run typecheck` + `npm run build` in `/frontend`; manual E2E of the Bob flow (restart backend — no auto-reload). **No DB migration; no `alembic upgrade`.**
- **Success criteria**: (1) scrolling up is not interrupted by new messages, button appears; (2) "Extract from MCP: done" renders before the quality message; (3) no duplicate "Saved N…" bubble; (4) no placeholder; (5) unclear requirements trigger a per-file Q&A that edits the MD and re-checks, and select-id appears only after all points are cleared or skipped.

## Review adjustments (post-implementation)

An adversarial multi-dimension review of the diff surfaced 7 confirmed findings, all addressed before sign-off:

- **Per-file Skip only.** The clarify question bundles all of a file's unclear points, so a per-point Skip is meaningless — the redundant "Bỏ qua điểm này" button + `skip_point` action were removed; "Bỏ qua file này" (`skip_file`) is the single skip.
- **Stub/failed pages excluded** (`_is_clarifiable`): pages with empty `requirement_md` (failed conversion, never auto-saved) or the anti-hallucination stub marker never enter the loop, so clarify can't resurrect or fabricate a requirement the pipeline deliberately refused to generate.
- **Re-scan before save** (`_apply_clarification`): the rewritten MD is re-scanned and persisted with the *fresh* warnings, so the stored artifact's quality metadata matches its content.
- **Stale-answer guard:** a `clarify_answer` whose `page_id` is not the current queue head is never applied to a different requirement — the head is re-asked instead.
- **`hasNewMessage` reset on thread switch;** removed write-only `_clarify_done` dead state.

Verified: `mypy src` clean (84 files); backend `pytest` 1511 passed (incl. 13 new clarify tests), coverage 84.2%; FE `typecheck`/ESLint/`build` clean; FE vitest 289 passed. No DB migration.

## Sprint-status note

No epic added/removed/renumbered and no story IDs change — Epic 11 stays `done`; this is an in-place UX refinement. `sprint-status.yaml` update = N/A.
