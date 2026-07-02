<!-- markdownlint-disable MD013 MD033 MD041 -->
# Code Review Findings — Epic 12 (Mary) + Epic 13 (Sarah)

- Date: 2026-06-17
- Reviewer: bmad-code-review (adversarial multi-layer + verification)
- Baseline: working tree vs HEAD `79f3f3c` (uncommitted changes, incl. untracked new files)
- Scope: all 13 stories in `review` status (12-1…12-5, 13-1…13-8); ~13k line diff, 35 files
- Method: 23 review agents (4 Blind Hunter + 4 Edge Case Hunter + 13 Acceptance Auditor + 2 Test Quality), each finding adversarially verified against the real code
- Result: 77 raw → 77 deduped → **50 confirmed real** (6 high, 14 medium, 30 low — effective/post-verification severity), **27 dismissed** as false-positive, **0 layers failed**

> Severity shown is the post-verification (corrected) severity. `[Cnn]` ids reference the full workflow output.

## Applied — 2026-06-17

**All 28 patch items APPLIED** (decision cluster resolved to "implement to original ACs"). Applied via 11 conflict-free per-file fix agents + orchestrator follow-up.

Full verification (clean):

- `uv run ruff check src tests` → All checks passed
- `uv run mypy src` → no issues in 80 source files
- `uv run pytest --no-cov` → **1417 passed** (1 known StarletteDeprecationWarning)
- `npm run typecheck` (now functional — `tsc -p tsconfig.app.json`) → clean
- `npm run lint` → clean · `npm run test` (vitest) → **272 passed** (24 files)

Orchestrator follow-up fixes (beyond the 28, required to keep gates green):

- `tests/integration/test_project_scoped_agents.py` — seeded requirement now carries `source_type="confluence"` (was a draft; the new C30 approved-only filter correctly excluded it).
- `frontend/src/components/ProviderSelector.tsx` — `JSX.Element` → `ReactElement` (React-19 namespace; pre-existing, surfaced by the C9 typecheck fix).
- `frontend/src/components/projects/ProjectPicker.test.tsx` — mock `Project` gained `jira_base_url`/`enabled_providers` (pre-existing, surfaced by C9).
- Ruff cleanup in `test_sarah.py` (dropped redundant `AgentState as SS` in-function imports → use top-level `AgentState`; unused imports) and `test_script_generator.py` (N801 class renames `…AC13_3`→`…AC133`, `…AC13_4`→`…AC134`).

**C6 RESOLVED (2026-06-17):** verified against the **live** MCP server — the correct param is **`issueKey`** (tool `corp_jira_get_issue`). Both snake_case `issue_key` AND the best-guess `issueIdOrKey` are rejected (`-32602 Input validation error … path: ["issueKey"] message: "Required"`). `jira_reader.py:189` corrected to `issueKey`; regression test `TestReadIssueRequestPayload` (3 tests asserting the payload uses `issueKey`, never `issue_key`/`issueIdOrKey`) added to `tests/pipelines/test_jira_reader.py`. `pytest tests/pipelines/test_jira_reader.py` → 22 passed; ruff clean. No open caveats remain.

## Summary counts

- `decision-needed`: 1 cluster (3 findings) — **RESOLVED 2026-06-17 → implement to original ACs (now patches)**
- `patch`: 50 findings → 28 unique items (incl. the 3 resolved decision findings)
- `defer`: 0
- `dismissed`: 27

---

## Decision-needed (RESOLVED)

> **Resolution (Thuong, 2026-06-17): Implement to the original ACs.** C30 → add the unconditional `source_type IS NOT NULL` filter; C35 → add the AC3 precondition gate; C7 → re-check the 12.1 task boxes once the work lands. All three are reclassified as **Patch — High** (see "Patch — 12.1 scope (resolved from decision-needed)" below).

- [x] `[Review][Decision]` **Story 12.1 acceptance bar — "approved-only inputs" + "block when no approved requirement" [C7, C30, C35]** — Story 12.1 was redefined on 2026-06-16 (multi-select → single-id-at-Bob). The verification correctly dismissed the *old* multi-select ACs (D18/D20/D21). **But three gaps survived verification because they are independent of that redefinition:**
  - [C30] `mary.py:117-144` — when `selected_id` is empty/unresolved (no Bob handoff, or `mary_selected_id.json` absent/unparseable), `process()` falls back to `load_requirement_markdown()` with **no `source_type` filter**, so **draft requirements (`{page_id}.md`, provenance NULL) are fed to the LLM** alongside approved ones. The same happens when a `selected_id` is present but not found (warn + "generate from all").
  - [C35] `mary.py:64-91` — AC3 ("no approved requirement → Mary blocks, no PROCESSING, UX-DR12 message") is **not implemented**: `handle_start` unconditionally `transition_to(PROCESSING)`, then returns `success, data=[]` and goes to DONE with a generic warning. No `_check_preconditions` / `_format_no_requirements_message` (Sarah and Bob both have one).
  - [C7] `12-1-...md:90-143` — **process-integrity:** every Task 1-8 checkbox is `[x]`, yet the story's own Completion Notes say those items were "NOT built (intentionally)". The binding AC1-AC3 text was never amended to the redefined flow, so 12.1 sits in `review` with its written ACs unmet.
  - **Decision required:** is the "approved-only + block-when-none" behavior still in scope (→ implement the unconditional `source_type IS NOT NULL` filter + an AC3 precondition gate, then re-check the boxes), or was it deliberately descoped (→ amend AC1-AC3 in `epics.md` + this story and correct the task checkboxes)? Either way the draft-leak (C30) is a real data-integrity hole that should be closed regardless.

---

## Patch — 12.1 scope (resolved from decision-needed)

- [ ] `[Review][Patch]` **AC1: Mary must use approved requirements only — filter drafts unconditionally [C30]** `src/ai_qa/agents/mary.py:117-144` — apply `source_type IS NOT NULL` before any `selected_id` narrowing, so the empty/unresolved-selected_id fallback can never feed draft `{page_id}.md` requirements to the LLM.
- [ ] `[Review][Patch]` **AC3: Mary must block when no approved requirement exists [C35]** `src/ai_qa/agents/mary.py:64-91` — add a `_check_preconditions` / `_format_no_requirements_message` gate at the top of `handle_start` (mirror Sarah/Bob): no PROCESSING transition, no LLM call, emit a UX-DR12 message telling the user to run Bob and approve ≥1 requirement first.
- [ ] `[Review][Patch]` **Reconcile 12.1 story checklist with shipped code [C7]** `12-1-...md` — once C30/C35 land, re-verify each AC has code + tests and the Task 1-8 checkboxes reflect reality (no `[x]` on work the Completion Notes say was "not built").

## Patch — High

- [ ] `[Review][Patch]` **Sarah edit buffer is wiped for ALL scripts whenever any sibling is approved/skipped/rejected [C1]** `frontend/src/components/agents/SarahScriptReviewPanel.tsx` (reset effect ~L125-131) — the reset keys on `scripts` array identity, but the backend re-presents the full list (new array ref) on every approve/skip, so per-script edits are silently discarded mid-review. Fix: prune `edits` to entries whose `script_content` is unchanged, or gate the reset on a generation discriminator. (test guard: [C10])
- [ ] `[Review][Patch]` **Rejected test case keeps its approval stamp + reviewed status when regeneration fails [C2]** `src/ai_qa/agents/mary.py:373-388` — `_reviewed_indices.discard(index)` and `approved_by/at = None` are nested inside `if result.success and result.data:`; on regen failure/empty the rejected case stays approved & reviewed and is re-presented with no error. Fix: move the discard + stamp-clear outside the success guard; send UX-DR12 on failure; keep the case un-reviewed. (AC3 of 12.4)
- [ ] `[Review][Patch]` **Failed-generation placeholder scripts can be approved & saved as approved Playwright artifacts without validation [C3]** `src/ai_qa/agents/sarah.py` handle_approve (placeholder at ~L386-395) — an un-edited `# Generation failed: …` placeholder (`error_message` set) can be approved → saved as `kind=playwright_script` with `approved=True`, poisoning Epic 15 execution eligibility. Fix: reject approval when `current_script.error_message is not None` (skip-only), optionally validate un-edited content before persist.
- [ ] `[Review][Patch]` **Stale Sarah run state persists across runs/threads; re-entry guard skips the input-selection gate [C4]** `src/ai_qa/agents/sarah.py` handle_start (re-entry guard ~L697-699) — agent is cached per `(user,project,step)` (no thread_id); `handle_start` never resets `confirmed_test_cases`/`candidate_test_cases`/`_generated_scripts`/`_reviewed_indices`, so a fresh re-run or thread-switch reuses the prior selection and regenerates the wrong scripts. Fix: reset per-run state at the top of `handle_start`; use a dedicated flag for the chrome-path re-entry instead of overloading `confirmed_test_cases`.
- [ ] `[Review][Patch]` **Duplicate/empty test-case titles collapse N approved test cases into 1 [C5, C14]** `src/ai_qa/agents/mary.py` `_write_approved_test_cases` + `src/ai_qa/pipelines/artifact_adapter.py:137-185` `save_test_case` (idempotent-by-name) — two cases with the same title (or empty title → `.json`) produce the same name; saving case #2 deletes case #1's just-saved artifact, yet DONE still reports "N saved". Fix: make per-case names unique (append index or `source_requirement_id`); explicit fallback for empty filenames.
- [x] `[Review][Patch]` **Jira MCP tool called with snake_case `issue_key`; the server expects __SKIP_WORD_0_camcorpse__ [C6]** `src/ai_qa/pipelines/jira_reader.py:189` — **RESOLVED & live-verified: correct param is `issueKey`** (not `issueIdOrKey`). Both snake_case and `issueIdOrKey` are rejected by the live server. Regression test `TestReadIssueRequestPayload` added. (See "Applied" note above.)

## Patch — Medium

- [ ] `[Review][Patch]` **Stale `marySelectedId` leaks across thread switches [C8]** `frontend/src/App.tsx:664-681` — `marySelectedId` is never reset on thread change, so Mary auto-start sends the prior thread's id, shadowing the new thread's persisted `mary_selected_id.json`. Fix: `setMarySelectedId("")` in the threadId effect.
- [ ] `[Review][Patch]` **`message.result?.data` references a property that does not exist on `AgentMessage` (TS2339), masked by a no-op typecheck script [C9]** `frontend/src/App.tsx:833` + `frontend/package.json` — `npm run typecheck` (`tsc --noEmit` with `files:[]`) compiles zero files and passes; `tsc --build` reports the real error. Fix: drop the dead `message.result?.data` fallback **and** fix the `typecheck` script to actually check the app (`tsc -b` / `-p tsconfig.app.json`) so this class of error is caught.
- [ ] `[Review][Patch]` **MaryReviewPanel loses all resolved/nav state on every reject (panel unmounts during PROCESSING, never re-syncs) [C11]** `frontend/src/components/agents/MaryReviewPanel.tsx` — `resolvedIndices`/`currentIndex` are local state with no server re-derivation; after a reject the panel remounts and the "(N resolved)" counter resets to 0 / view jumps to case 0. Fix: add `useEffect([testCases])` to rebuild `resolvedIndices` from `tc.approved_at` (mirror Sarah's status-sync).
- [ ] `[Review][Patch]` **`handle_reject` takes `result.data[0]` → replaces rejected case with an unrelated case and drops siblings [C12, C13]** `src/ai_qa/agents/mary.py:369-380` — when the source can't be narrowed, regeneration runs over all requirements and `data[0]` (first case of first requirement) overwrites `test_cases[index]`; for a multi-case requirement the other regenerated cases are discarded and stale ones remain. Fix: scope regeneration to the single rejected requirement, or define explicit group-replacement semantics; never assume `data[0]` is the rejected case.
- [ ] `[Review][Patch]` **`source_test_case_id` provenance lost on reject→regenerate→approve [C15, C16]** `src/ai_qa/agents/sarah.py` `_regenerate_current_script` (~L475-481) — the replacement `GeneratedScript` omits `source_test_case_id`, so the approved script's metadata sidecar loses the source-test-case link (AC2 of 13.8). Fix: carry `current_script.source_test_case_id` forward (and on the regen-failure placeholder too); add a reject→regen→approve regression test.
- [ ] `[Review][Patch]` **Script filename collision: distinct test-case titles collapse to one saved script + sidecar [C17, C18]** `src/ai_qa/agents/sarah.py` (~L791-794) + `artifact_adapter.py:214-257` `save_script` (idempotent-by-name) — two titles that normalize to the same `test_<x>.py` (e.g. both "Untitled Test Case") cause the second approve to delete the first's approved artifact; the sidecar uses a different stem and also collides (last write wins). Fix: disambiguate generated names per case; derive sidecar name from the saved `.py` stem.
- [ ] `[Review][Patch]` **Mary's `selected_id` requirement-scoping branch in `process()` is entirely untested [C19]** `tests/test_agents/test_mary.py` — all `process()` tests pass empty `input_data` and stub `load_metadata=None`, so the selected_id resolution / persisted-metadata fallback / target-filter / not-found-warning are never exercised. Fix: add the 3 missing branch tests.
- [ ] `[Review][Patch]` **No test guards the AC1 rule "invalid edited script must NOT re-emit `script_review`" [C20]** `tests/test_agents/test_sarah.py` — the invalid-edit tests assert no save / state unchanged, but never assert that no `metadata.type=='script_review'` was broadcast (which would overwrite the client edit buffer). Fix: add that assertion.

## Patch — Low

- [ ] `[Review][Patch]` **Unused `cast` import in `models.py` → Ruff F401 fails the lint gate [C40, C41, C42]** `src/ai_qa/models.py:15` — remove `cast` from the import (`uv run ruff check src` reports exactly this one error).
- [ ] `[Review][Patch]` **Unused `os`/`pytest` imports in new test file → Ruff F401 [C48]** `tests/pipelines/test_script_validator.py:6,9` — remove both.
- [ ] `[Review][Patch]` **Non-numeric `test_case_index` crashes Mary handle_approve/reject [C33]** `src/ai_qa/agents/mary.py:238-242, 313-317` — `int(data["test_case_index"])` runs before the bounds clamp; `"abc"`/`None`/list raises and bubbles to a generic WS error. Fix: parse defensively, fall back to `current_review_index`.
- [ ] `[Review][Patch]` **Non-numeric `script_index` crashes Sarah handle_approve/reject/skip [C37, C38]** `src/ai_qa/agents/sarah.py` (3 sites, ~L749/839/899) — same pattern. Fix: try/except around `int()`, degrade to the out-of-range warning.
- [ ] `[Review][Patch]` **Fallback index can be out-of-range → IndexError / wrong stamp on stray approve [C31]** `src/ai_qa/agents/mary.py:243-255` — when `test_case_index` is out of range the fallback `current_review_index` may equal `len(test_cases)`; `test_cases[index]` then raises. Fix: re-clamp the fallback into range and guard empty list (apply in handle_reject too).
- [ ] `[Review][Patch]` **`_format_review_content` shows "No test case to review" on the save-failure re-present [C34]** `src/ai_qa/agents/mary.py:407-415, 492-495` — after the last approval `current_review_index == len`; a save-failure re-present renders the empty-guard text while the full list is still attached. Fix: clamp the display index.
- [ ] `[Review][Patch]` **Dead branch: low-confidence skip guard in handle_approve can never trigger [C32]** `src/ai_qa/agents/mary.py:235-243` — once `all_reviewed` is true the set already contains every index, so `_unresolved_low_confidence_indices()` is always `[]`. Fix: remove the inert block or relocate the guard so it can gate before completion.
- [ ] `[Review][Patch]` **Repeated same-index approve never reaches DONE and gives no "remaining" signal [C36]** `src/ai_qa/agents/mary.py:258-266, 295-301` — overlaps C31/C33; surface the unreviewed index set and ensure in-range fallback.
- [ ] `[Review][Patch]` **Mary/Sarah review state not restored on history replay (page reload / project re-select) [C24]** `frontend/src/App.tsx:882-887` — the replay forEach only calls `handleAliceMessage`/`handleBobMessage`; a persisted `test_case_review`/`script_review` is not replayed, so the panel renders empty. Fix: add `handleMaryMessage`/`handleSarahMessage` to the replay loop.
- [ ] `[Review][Patch]` **Dead `jira_url` start-payload branch + dead `jiraUrl` state [C25]** `frontend/src/App.tsx:177, 506, 1132-1133` — the only inputs that wrote `bobState.jiraUrl` were removed; the start-payload branch is now permanently unreachable. Fix: remove the dead branch/state (Jira now rides the post-extraction select-id step).
- [ ] `[Review][Patch]` **AC1 approval caption not surfaced for the final-approved script [C39]** `src/ai_qa/agents/sarah.py:817-829` — the DONE path never re-presents, so the last script's `approved_by/at`/`status` never reach the panel. Fix: re-emit `_present_script_review()` once before `transition_to(DONE)`, or derive the caption from local `resolvedIndices`.
- [ ] `[Review][Patch]` **Script provenance sidecar (`save_metadata`) is not idempotent-by-name [C43]** `src/ai_qa/pipelines/artifact_adapter.py:263-280` — `save_script` is now idempotent but its sidecar isn't, so reject→regen→re-approve accumulates duplicate `{filename}.metadata.json` rows that `load_metadata` resolves non-deterministically. Fix: make the sidecar idempotent-by-name, or have `load_metadata` return the latest row.
- [ ] `[Review][Patch]` **Hardcoded-secret detector ignores username literals despite AC1/AC3 wording [C44]** `src/ai_qa/pipelines/script_generator.py:42-45` — `_CRED_KEYWORD_RE` has no `username`/`user`/`login`/`email` token, so `get_by_label("Username").fill("admin")` is not flagged though AC1/AC3 enumerate "usernames". Fix: add the username keywords (or explicitly document that usernames are excluded as non-secret).
- [ ] `[Review][Patch]` **Custom `script_unsafe_patterns` override can't register a bare custom call name [C45]** `src/ai_qa/pipelines/script_validator.py:281-288` — a bare token (no dot, not in `_UNSAFE_CALL_NAMES`) is routed only to `import_denylist`, never checked against `ast.Call`. Fix: treat bare override tokens as both import and call candidates (or document the dotted-path requirement). Deployment-only, low impact.
- [ ] `[Review][Patch]` **Low-confidence override rationale quotes the pre-penalty `structural_score` not the displayed post-penalty score [C46]** `src/ai_qa/pipelines/test_case_extractor.py:416-419` — re-introduces the contradiction step 5 was meant to remove (the spec example interpolates `{score}`). Fix: use the post-penalty `score` for both the gate and the message.
- [ ] `[Review][Patch]` **(test) SarahScriptReviewPanel edit-buffer reset-on-new-payload untested [C10]** `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx` — add an RTL `rerender` test (guards [C1]).
- [ ] `[Review][Patch]` **(test) No Mary-level multi-requirement grouping/contiguity test [C21]** `tests/test_agents/test_mary.py` — add a two-requirement test asserting per-source contiguity + grouping summary (Task 5 of 12.2).
- [ ] `[Review][Patch]` **(test) No App.tsx WS round-trip / index-addressable wiring test [C23]** `frontend/src/App.tsx` — add an App/hook-level test feeding a 2-item review payload and asserting the correct outbound index.
- [ ] `[Review][Patch]` **(test) MaryReviewPanel auto-advance-to-next-unresolved untested [C26]** — add a 2/3-case advance test.
- [ ] `[Review][Patch]` **(test) MaryReviewPanel `disabled` prop untested [C27]** — assert Approve/Reject/nav are disabled when `disabled`.
- [ ] `[Review][Patch]` **(test) Confidence-rationale toggle doesn't assert pre-click hidden state [C28]** — assert absent before click, present after, hidden after second click.
- [ ] `[Review][Patch]` **(test) SarahScriptReviewPanel status-sync + "N of M reviewed" counter untested [C29]** — assert the counter text and per-dot aria-labels.
- [ ] `[Review][Patch]` **(test) `test_confidence_unchanged_by_13_3/13_4_detectors` are tautological [C47]** `tests/pipelines/test_script_generator.py` — they compare a pure function to itself; rewrite to compare clean vs pattern-laden scripts.
- [ ] `[Review][Patch]` **(test) Confidence boundary/band tests assert ranges, not exact thresholds; comment math is wrong [C49]** `tests/pipelines/test_test_case_extractor.py` — pin the exact 0.80/0.55 boundaries (account for the test_data component) and fix the comments.
- [ ] `[Review][Patch]` **(test) Grouping-summary / low-confidence broadcast assertions are over-loose [C50]** `tests/test_agents/test_mary.py` — match the specific summary substring and "low confidence" phrasing, not generic `requirement`/`generated`/`⚠`.
- [ ] `[Review][Patch]` **(doc) 13-5 File List claims an E2E panel-assertion block that is absent from `epic-13.spec.ts` [C22]** — either add the env-gated block or correct the File List + Completion Note #8 (E2E was deferred to Vitest per Confirmed Decision #4).

---

## Dismissed (27 — false-positive / not-real, dropped)

Most were rejected because they (a) judged code against the **superseded** 12.1 multi-select ACs (D18, D20, D21, D22), (b) cited **pre-existing/unchanged** code (D10, D11, D14, D15), or (c) described a real code shape whose claimed consequence does not follow given the actual contract (D5, D6, D7, D17). Notable: **D5/D6** (Sarah `index` vs array-position mismatch) were refuted because the backend payload's `index` equals array position; **D7** (auto-navigate timer) mirrors an accepted pre-existing pattern. Full rationale per item is in the workflow output.
