# Investigation: Bob parse has no resume — interruption mid-batch forces a full re-parse

## Hand-off Brief

1. **What happened.** Bob extracts Confluence pages in a sequential batch; when the run is interrupted mid-batch (server restart / process death), the reconciler resets the thread to `start`, the FE drops the user back to Bob's intake form, and re-submitting re-runs the **entire** extract+convert chain from scratch — already-converted pages are re-fetched (Phase 1) and re-converted by the LLM (Phase 2) (Confirmed).
2. **Where the case stands.** Root cause is Confirmed end-to-end (BE + FE): `_extract_descendants` resets `self.pages = []` and iterates all pages with no skip-check, even though the read-back machinery for saved requirements already exists (`_load_saved_requirement_pages`, the "skip" path, idempotent re-approve). Per-page `.md` artifacts survive the interruption, so resume is feasible and largely a matter of wiring existing parts together.
3. **What's needed next.** Decide UX: transparent auto-skip inside `_extract_descendants` (no new button — every re-run becomes a cheap resume) vs. an explicit "Continue" button gated on detected saved progress. Then implement via `bmad-create-story` / `bmad-quick-dev`.

## Case Info

| Field            | Value                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                    |
| Date opened      | 2026-06-23                                                                              |
| Status           | Active                                                                                  |
| System           | Win11 dev (`uvicorn --reload`) + UAT container; Bob agent, FastAPI + WS pipeline        |
| Evidence sources | Screenshot (Bob step), `src/ai_qa/agents/bob.py`, `src/ai_qa/threads/service.py`, `project-context.md`, memory `stuck-thread-startup-recovery` |

## Problem Statement

User (verbatim, VI): *"parsing fail giữa chừng nhưng không có cơ chế retry. Hãy thêm vào nút Continue để parse tiếp tục document tiếp theo trong trường hợp có lỗi."*

Translation: parsing fails midway but there is no retry mechanism; the user wants a **Continue** button that resumes parsing from the next document after an error.

Screenshot shows Bob — Requirements (Step 2 of 5): a sequence of `Parsing '…'` / `✓ Converted '…'` messages, ending at `Parsing 'DLee - PT form page'...` followed by a system warning: *"⚠ The previous run was interrupted because the server restarted. Please start this step again."*

**Premise check (early):** the user's framing conflates two different failure modes. Evidence shows per-page *conversion errors* are already handled (loop continues); the screenshot symptom is a *whole-run interruption* (process death), and the real gap is the **lack of resume** on the subsequent re-run, not a missing per-page retry. See Findings 1–3.

## Evidence Inventory

| Source                                   | Status    | Notes                                                                                  |
| ---------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| Screenshot of Bob step                   | Available | Confirms symptom: interrupted mid-batch + "Please start this step again."              |
| `src/ai_qa/agents/bob.py` (parse loop)   | Available | Phase 1 fetch `1023-1048`; Phase 2 parse/convert `1118-1199`; `self.pages = []` `1119` |
| `src/ai_qa/threads/service.py`           | Available | `reconcile_interrupted_work()` `264-318`; interrupted message `309-312`                |
| `src/ai_qa/pipelines/artifact_adapter.py`| Available | `save_requirement_page` `49-53` → `_save_text(kind="requirements")` (durable per page) |
| Frontend Bob step / "Start" button       | Missing   | Not yet located — where the Start affordance + WS `start` action is rendered           |
| Caller chain into the parse method       | Partial   | `handle_start` `556`; batch loop appears inside `_extract_descendants` (`906`+) — confirm |
| Prior case `bob-stuck-parsing-thread1`   | Available | Related (the interruption/reconcile mechanism); distinct from this resume gap          |

## Investigation Backlog

| # | Path to Explore                                                                 | Priority | Status | Notes                                                            |
| - | ------------------------------------------------------------------------------- | -------- | ------ | ---------------------------------------------------------------- |
| 1 | Confirm enclosing method of the `1118-1199` loop + its caller from `handle_start` | High     | Done   | `_extract_descendants` (`906`), called from `handle_approve` (`1940`) after parent-confirm — Finding 5 |
| 2 | Frontend Bob step: how "Start" is rendered post-reconcile; feasibility of "Continue" | High     | Done   | `status=="start"` → Bob intake form (`App.tsx:2295`); "Start" is a status badge, not a button — Finding 6 |
| 3 | Can the loop read back already-saved `.md` to skip? (`_load_saved_requirement_pages` `1904`) | High     | Done   | Yes — read-back machinery exists; `_extract_descendants` just doesn't use it — Finding 7 |
| 4 | Does Phase 1 (raw-HTML re-fetch, `1023-1048`) also need skipping, or only Phase 2? | Medium   | Open   | Phase 2 (LLM convert) is the expensive part; Phase 1 is MCP I/O — both re-run today |
| 5 | Should resume be automatic on `start`, or a distinct user-triggered action?     | Medium   | Open   | **UX decision for Thuong** — affects scope (BE-only auto-skip vs. FE+BE button) |

## Confirmed Findings

### Finding 1: Per-page conversion failures are already handled — they do NOT abort the batch

**Evidence:** `src/ai_qa/agents/bob.py:1166-1199`

**Detail:** The convert step is wrapped in `try/except`. On failure it logs, emits `⚠ Failed to convert: '{title}'`, appends a stub page (empty `requirement_md` + a warning), and the `for` loop **continues** to the next page. An empty/near-empty source is likewise stubbed and skipped (`1135-1164`). So a single page's LLM/convert error does not stop the run — the "no retry" the user observed is not this path.

### Finding 2: The screenshot symptom is a whole-run interruption (process death), recovered by the reconciler

**Evidence:** `src/ai_qa/threads/service.py:264-318` (message string `309-312`); `project-context.md:162`; memory `stuck-thread-startup-recovery`.

**Detail:** A worker restart (`uvicorn --reload`), crash, OOM, or kill terminates the in-flight asyncio pipeline task by *process death* — no Python exception runs, so Finding 1's `try/except` never fires. On the next boot, `reconcile_interrupted_work()` (FastAPI lifespan, `api/app.py:92`) flips threads stuck at `processing` → `start` and appends the exact system message seen in the screenshot. This is the documented `--reload` mid-run hazard.

### Finding 3: Re-running "Start" re-does the entire batch — there is no resume/skip (root cause of the user's complaint)

**Evidence:** `src/ai_qa/agents/bob.py:1119` (`self.pages = []`), `1120-1199` (full `for page in raw_pages` loop), `1023-1048` (Phase-1 re-fetch).

**Detail:** When the user presses "Start" after reconcile, Bob re-enters the batch: it resets the accumulator, re-fetches **all** raw pages from Confluence (Phase 1), and re-parses + re-converts **every** page (Phase 2). There is no check that consults already-persisted progress to skip completed pages, so all prior work (e.g. the three `✓ Converted` pages in the screenshot) is redone from zero. This is the missing "retry/continue" capability.

### Finding 4: Already-converted pages persist durably per-iteration → resume is feasible

**Evidence:** `src/ai_qa/agents/bob.py:1143` & `1170` call `adapter.save_requirement_page(page.page_id, requirement_md)`; `src/ai_qa/pipelines/artifact_adapter.py:49-53` → `_save_text(kind="requirements", …)`. Phase 1 likewise persists raw HTML per page (`bob.py:1045`).

**Detail:** Each page's requirement `.md` (and raw HTML) is saved at the moment it is produced, before the loop advances — so converted artifacts survive the interruption. A resume that skips pages with an existing saved `.md` would avoid re-doing LLM work. `handle_approve` already reloads saved pages via `_load_saved_requirement_pages(adapter)` (`bob.py:1904`), establishing a read-back precedent.

### Finding 5: Caller chain — the batch lives in `_extract_descendants`, invoked from `handle_approve`

**Evidence:** `bob.py:556` (`handle_start`) → `636` (`process`) → `649-664` (emits `is_confirm_parent`, REVIEW_REQUEST) → user approves → `handle_approve:1879` → `1881` (`phase=="confirm_parent"`) → `1940` (`await self._extract_descendants(confirmed_page)`).

**Detail:** The expensive batch (Phase 1 fetch + Phase 2 parse/convert, `bob.py:1023-1199`) runs inside `_extract_descendants`, which is reached only after the user confirms the parent page. The interruption in the screenshot occurred here, while `thread.status == "processing"`. Because `self.phase` is in-memory agent state, process death discards it; the thread is reset to `start` (Finding 2), so on the next run the user must re-enter the URL, re-confirm the parent, and re-trigger the full batch.

### Finding 6: At `status=="start"` the FE renders Bob's intake form — "Start" is only a status badge

**Evidence:** `frontend/src/App.tsx:2295-2297` (intake form gated on `status === "start" || bobState.submittedMcp`), `App.tsx:1855` & `components/AgentTopBar.tsx:84` (the "Start" pill is a `StatusBadge`, not a button).

**Detail:** The user-facing "retry" affordance after reconcile is Bob's intake form (`handleBobStart`), not a dedicated button. So a "Continue" button does not exist today and would be a new FE element; alternatively, resume can be made transparent so the normal form re-submit becomes a cheap resume with no UI change.

### Finding 7: The resume machinery already exists — `_extract_descendants` simply never uses it

**Evidence:** `_load_saved_requirement_pages` (`bob.py:1838-1861`) + `adapter.load_requirement_markdown()`; the "skip" path (`handle_approve:1886-1919`) already loads saved requirements instead of re-extracting; the save step is already idempotent with a re-approve retry (`bob.py:1954-1968`, *"re-approve re-runs the save"*).

**Detail:** Reading back already-saved requirement artifacts is a solved, used pattern elsewhere in Bob. The defect is narrow: `_extract_descendants` (`bob.py:1119-1199`) unconditionally clears `self.pages` and re-runs both phases for every page, never consulting `adapter.load_requirement_markdown()` to skip pages whose `.md` already exists. The fix reuses existing parts rather than inventing new persistence.

## Source Code Trace

| Element       | Detail                                                                                       |
| ------------- | -------------------------------------------------------------------------------------------- |
| Error origin  | Not an exception — process death of the pipeline task inside `_extract_descendants` (`bob.py:1120` loop) |
| Trigger       | Worker restart/crash during a multi-page Bob batch (`uvicorn --reload`, OOM, kill) — chain: `handle_start`→`process`→confirm_parent→`handle_approve:1940`→`_extract_descendants` |
| Condition     | On reboot, `reconcile_interrupted_work()` (`service.py:264`) resets thread `processing`→`start`; FE shows the intake form (`App.tsx:2295`); re-submit re-runs the full batch with no skip (`bob.py:1119`) |
| Related files | `bob.py` (`_extract_descendants` `906`, `handle_approve` `1879`, `_load_saved_requirement_pages` `1838`), `threads/service.py:264` (reconcile), `pipelines/artifact_adapter.py:49` (per-page persistence + `load_requirement_markdown`), `frontend/src/App.tsx:2295` (intake form) |

## Conclusion

**Confidence:** High (root cause Confirmed end-to-end, BE + FE)

The real defect is the **absence of resume**, not a missing per-page retry. Per-page conversion errors are already tolerated (Finding 1). The screenshot shows a whole-run interruption recovered by the reconciler (Finding 2); the subsequent re-run re-does the entire extract+convert batch because `_extract_descendants` clears `self.pages` and re-processes every page, never consulting persisted progress (Findings 3, 5). Each page's `.md` is saved durably per iteration (Finding 4) and Bob already has read-back machinery (`_load_saved_requirement_pages`, the "skip" path, idempotent re-approve — Finding 7), so a resume that skips already-saved pages is feasible by wiring existing parts together. The only open question is UX (Findings 6 + Backlog #5): transparent auto-skip vs. an explicit "Continue" button.

## Recommended Next Steps

### Fix direction

Two viable approaches; **Option A recommended** (smaller, BE-only, no new UI, benefits every re-run):

- **Option A — transparent idempotent resume (recommended).** In `_extract_descendants`, load the set of already-saved requirement page ids once (via `adapter.load_requirement_markdown()` / the `_load_saved_requirement_pages` pattern) before the loop. For each page already having a saved `.md`, **skip the LLM `formatter.convert_markdown` call** and hydrate `self.pages` from the saved artifact instead. Phase 1 raw-HTML fetch can likewise be skipped when the raw artifact already exists (Backlog #4). Net effect: re-submitting the intake form after an interruption resumes from the next un-converted page automatically — no FE change. Keep a "force re-extract" escape hatch (the existing flow when no saved artifacts exist, or an explicit override) so users can still refresh changed Confluence content.
- **Option B — explicit "Continue" button.** Detect saved-but-incomplete progress for the project and render a "Continue extraction" action (new FE element near the intake form, Finding 6) that calls the start path in resume mode. More work (FE + BE + a "is there partial progress?" signal) and largely subsumes Option A's BE change anyway.

Recommendation: implement Option A; it directly satisfies "parse tiếp tục document tiếp theo" without a new button, and a Continue button can be layered on later if desired.

### Diagnostic / verification

- Add a unit test around `_extract_descendants` asserting that, when a page's requirement `.md` already exists, `formatter.convert_markdown` is **not** called for it and the saved content is reused.

## Reproduction Plan

1. Start a Bob requirements run on a parent page with several child pages (on a slow on-prem model exaggerates the window).
2. While the `Parsing '…'`/`✓ Converted '…'` messages are streaming (a few pages converted, more pending), restart the backend (`uvicorn --reload` triggered by any file save, or kill the worker).
3. On reboot, observe the thread reset to `start` with the system message "⚠ The previous run was interrupted…" (`service.py:309`).
4. Re-submit Bob's intake form → observe that **all** pages, including the already-converted ones, are re-fetched and re-converted from scratch (current behaviour). Expected after fix: already-saved pages are skipped and only un-converted pages run.

## Status

Concluded — root cause Confirmed end-to-end (High confidence). Ready for implementation; one open UX decision (Option A vs. B, Backlog #5). Backlog #4 (skip Phase-1 raw fetch) folds into the chosen fix.
