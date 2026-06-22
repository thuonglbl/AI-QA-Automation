# Sprint Change Proposal — Mary Test-Case UX Polish (2026-06-20)

**Trigger:** Mary now generates test cases correctly, but four UX/format issues surfaced during live review.
**Mode:** Batch (changes were small, well-scoped, and independently verifiable).
**Scope classification:** Minor — direct implementation, no replan. No schema/migration. No commit (Thuong commits himself).

## Section 1 — Issue Summary

After Mary's per-item review flow went live (Epic 12), Thuong flagged four issues:

1. Test cases are persisted as **JSON** files; he wants **Markdown** so the artifacts are friendly for LLMs (and humans).
2. Mary's files appear in the **Reports** sidebar folder; Reports should be reserved for Bob's domain.
3. The left sidebar is too narrow to show full file names.
4. The chat shows a redundant Markdown dump per case (`## Test Case 27 of 35 … **Confidence:** 🔴 LOW (0.85) …`) even though the `MaryReviewPanel` below already renders the same case with approve/reject controls.

## Section 2 — Impact Analysis

- **Mary (`agents/mary.py`):** test-case artifacts are written by `_persist_test_case` as `{base}.json` (`model_dump_json`). Needs to emit Markdown.
- **Sarah (`agents/sarah.py`):** consumes test cases by `json.loads(artifact.content)` → `TestCase(**data)` at three sites (`_load_test_cases`, `_present_test_case_selection`, `_confirm_inputs`) and `ScriptGenerator` re-serializes via `model_dump_json`. Switching the body to Markdown would break parsing unless the structured object is preserved elsewhere.
- **Storage classifier (`artifacts/storage.py::folder_for_kind`):** test-case `.metadata.json` sidecars + `mary_selected_id.json` are `kind="configuration"` → routed to the `reports` catch-all → they pollute Reports.
- **Frontend:** sidebar width (`App.tsx` `<aside>`); the `test_case_review` carrier message renders as a chat bubble (`App.tsx` message filter); Reports folder renders all entries (`ProjectSidebar.tsx`).
- **No PRD / Architecture / UX-spec conflicts.** No DB schema change.

## Section 3 — Recommended Approach (revised after review)

**Direct Adjustment.** The original draft kept a JSON sidecar as the machine source of truth. Thuong rejected that: Sarah drives browser-use with **natural language**, so forcing a JSON read — and keeping JSON *and* Markdown — is illogical. Revised design: **Markdown is the single representation, end to end.**

- Mary persists **only** `{base}.md` (no JSON copy anywhere).
- `TestCase.to_markdown()` / `TestCase.from_markdown()` are inverses on the model. The Markdown is the serialization; the typed `TestCase` is reconstructed on demand.
- Sarah feeds the **Markdown** to the script-generation LLM (natural language), and reconstructs a `TestCase` from it only for the review panel / heuristics / filename. The reconstruction's accuracy never gates script generation (the LLM gets the raw Markdown regardless).
- Backward-compatible: legacy `.json` test cases still parse (JSON tried first).

## Section 4 — Detailed Change Proposals

### 4.1 Test cases → Markdown, end to end (`#1`)

- `models.py`: `TestCase.to_markdown()` (clean `#`/`##` sections — Objective/Source/Preconditions/Test Data/Steps/Expected Results/Automation Hints/Tags/Warnings, no review framing) + `TestCase.from_markdown()` (best-effort inverse). Round-trip tested.
- `mary.py::_persist_test_case`: save `{base}.md` via `tc.to_markdown()`; **removed the `.metadata.json` sidecar write entirely**. Provenance (`source_url`, `warnings`) rides on the artifact row.
- `sarah.py`: `_testcases_from_artifact()` — try legacy JSON content first (back-compat), else `TestCase.from_markdown(content)`. Wired into all three sites (`_load_test_cases`, `_present_test_case_selection`, `_confirm_inputs`). No sidecar/meta-map plumbing.
- `script_generator.py`: the 3 prompts (`SCRIPT_GENERATION_PROMPT`, `TRACE_TO_PLAYWRIGHT_PROMPT`, `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT`) are fed `test_case.to_markdown()` instead of `model_dump_json`; prompt labels changed `(JSON format)` → `(Markdown)`.

**Revision 2 — QA review is Markdown too (no structured JSON anywhere a human/LLM sees the test case):**

- `mary.py::_present_test_case_review`: the `test_case_review` payload no longer sends `tc.model_dump()` per case. New `_review_case_payload()` sends `{title, markdown, confidence, confidence_level, confidence_rationale, warnings, approved_at}` — the rendered Markdown document plus review-only chrome.
- FE `MaryReviewPanel.tsx`: renders the test case via `<ReviewContent>` (Markdown) instead of structured form fields; a leading `# Title` is stripped (the header already shows it). Confidence badge / low-confidence banner / nav / approve-reject unchanged. New `MaryReviewCase` type (`markdown` + chrome); `App.tsx maryState.testCases` retyped.
- **Decided — keep internal generation JSON (Thuong, 2026-06-20):** the *generation* step (`TestCaseExtractor`) keeps the LLM emitting JSON, parsed into the structured `TestCase` for confidence scoring + streaming. That JSON is an internal generation detail — never stored, shown to QA, or fed to Sarah — so it stays. (Rewriting the streaming JSON parser + confidence pipeline to Markdown was deemed not worth the risk for an invisible format.)
- **Trade-off:** `confidence_level` is review-time metadata and is not carried into the Markdown, so Sarah's selection-panel confidence badge is absent for new `.md` cases (test cases reaching Sarah are already approved). Mary's own review panel still shows the confidence badge (sent as chrome). Easy to re-add to Sarah later if wanted.

### 4.2 Reports for Bob only (`#2`)

- `ProjectSidebar.tsx::renderArtifactFolder`: for the `reports` folder, filter out `kind === "configuration"` (test-case metadata sidecars, `mary_selected_id.json`, `chrome_path.json`). Count badge follows the filtered set. Genuine report artifacts still show.

### 4.3 Wider sidebar (`#3`)

- `App.tsx`: `<aside>` width `w-[390px]` → `w-[585px]` (1.5×).

### 4.4 Drop the redundant review dump from chat (`#4`)

- `App.tsx` message filter: skip `msg.metadata?.type === "test_case_review"` bubbles. The `MaryReviewPanel` renders the same case; the carrier message stays in `messages` (timestamp lookup + reload-time panel restore unaffected). Backend content left intact (non-empty → not dropped by the WS gate).

## Section 5 — Implementation Handoff & Verification

**Status: implemented in the working tree (uncommitted).**

- `uv run ruff check` / `ruff format` — clean
- `uv run mypy src` — Success, no issues (84 files)
- `uv run pytest` (full suite) — **1553 passed**, coverage 83.9% (gate 80% met). New/updated tests: Markdown-only save, `to_markdown`/`from_markdown` round-trip, Sarah `from_markdown` reconstruction, `test_case_review` payload carries Markdown (no `steps`/`preconditions`).
- `npm run typecheck` — clean; `npx vitest run` — **306 passed** (incl. MaryReviewPanel rewritten to render Markdown).

**Notes / follow-ups for Thuong:**

- **Legacy data:** old `.json` test cases already in a project stay parseable (back-compat) but render as JSON-in-Markdown in the preview; regenerating a thread produces clean `.md`.
- **Confidence badge** in Sarah's selection panel is gone for new `.md` cases (confidence isn't carried into the Markdown). Re-add via a small front-matter line if you want it back.
- Restart the backend (no auto-reload) before live/E2E validation.
- Not yet live-validated end-to-end; commit (no migration needed) at your discretion.
