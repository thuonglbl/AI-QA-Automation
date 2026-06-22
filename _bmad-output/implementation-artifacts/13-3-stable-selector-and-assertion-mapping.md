---
baseline_commit: 2a1f170
---

# Story 13.3: Stable Selector and Assertion Mapping

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Sarah to prefer stable selectors and concrete assertions, and to flag brittle selectors and ambiguous expected results as review warnings tied back to their source test steps,
so that generated Playwright scripts are maintainable and reliable and I can see exactly where to look before approving.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.3](_bmad-output/planning-artifacts/epics.md) (lines 1302-1322), expanded with implementation defaults (see "Scope decisions" — **all four defaults CONFIRMED by Thuong 2026-06-13** ("hãy dùng hết default"); no pending input remains). This is the **selector/assertion specialization of Story 13.2** and the direct analog of **Story 12.3** (Mary's deterministic confidence-scoring): 13.2 built the generic review-marker channel (`# TODO:`/`# REVIEW:` + `GeneratedScript.warnings`); **13.3 specializes that same channel** with (a) brittle-selector flagging on top of the existing selector-priority guidance, (b) assertion-mapping warnings for unsupported/ambiguous expected results, and (c) warning text tied to the originating test step or expected result — **reusing 13.2's `warnings` surface, never inventing a parallel one**.

### AC1 — Selector priority preserved + brittle selectors flagged for review

- **Given** a generated script needs to locate UI elements
- **When** Sarah maps test steps to Playwright selectors
- **Then** selectors prefer `data-testid` → role-based (`get_by_role`) → accessible names → labels (`get_by_label`) → stable text (`get_by_text`) **in that priority order** (the existing prompt priority block — **keep** it; 13.3 strengthens, does not replace)
- **And** brittle selectors (XPath, raw CSS class/id, structural/positional `:nth-child`/`>`/descendant chains) that the model had to fall back to are **flagged for review** — surfaced as a categorized warning on `GeneratedScript.warnings` (and the inline `# REVIEW:` marker established in 13.2), **not silently emitted**

### AC2 — Expected results → concrete assertions where possible; unsupported/ambiguous ones remain visible as warnings

- **Given** a test case includes expected results
- **When** Sarah generates script assertions
- **Then** expected results are converted into concrete Playwright `expect(...)` assertions **where possible** (the existing assertion-mapping guidance — **keep** it)
- **And** expected results that are **unsupported or ambiguous** (no checkable/observable outcome, or fewer `expect()` assertions than declared expected results) **remain visible as review warnings** — surfaced on `GeneratedScript.warnings` (and the inline `# REVIEW:` marker from 13.2), never dropped or guessed into a fabricated assertion

### AC3 — Warnings tied to the source test step or expected result

- **Given** generated scripts include warnings
- **When** the user reviews them
- **Then** each selector/assertion warning **identifies its source** — a brittle-selector warning names the originating **test step** (via the nearest preceding `# Step N:` comment that 13.2 emits, best-effort) and an assertion warning names the **expected result** it relates to, so the (future Story 13.5) review UI can tie the warning back to the right place in the source test case

---

## ⚠️ Sequencing dependency (READ FIRST — critical)

**Story 13.3 builds directly on Story 13.2, which builds on Story 13.1, which builds on Epic 12. As of `2a1f170`, NONE of these are implemented** — Stories 12.1–12.5, 13.1 and 13.2 are all `ready-for-dev` and absent from the working tree. 13.3 is therefore **doubly-blocked**. Before starting, confirm the prerequisites are present in the live tree; **flag and stop** if missing — do NOT re-implement 13.2 / 13.1 / Epic 12 here.

What 13.3 assumes from upstream (verify present; reconcile against live code and note divergence in Completion Notes per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md)):

1. **13.2 (immediate prerequisite — the warning channel).** 13.2 adds `warnings: list[str]` to `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)), the `_extract_review_warnings(script_content) -> list[str]` helper in `ScriptGenerator._generate_single_script`, populates the per-case result `"warnings"` (today hardcoded `[]` at [script_generator.py:213](src/ai_qa/pipelines/script_generator.py:213)), threads warnings into `GeneratedScript(... warnings=...)` in `_generate_scripts` / `_regenerate_current_script`, adds `"warnings"` to the `review_data` payload ([sarah.py:714-725](src/ai_qa/agents/sarah.py:714)), establishes the `# TODO:` / `# REVIEW:` inline-marker convention in the prompts, adds the no-unsafe-inference rule, and rewrites `_generate_script_header` for durable source traceability. **13.3 extends every one of these surfaces** — it adds *new categorized detectors* that append to the **same** `warnings` list and *new prompt rules* on top of 13.2's marker convention. If `GeneratedScript.warnings` or `_extract_review_warnings` is absent, **13.2 is unmerged → 13.3 is blocked. Flag and stop.**
2. **13.1 (transitive prerequisite).** Sarah's lifecycle is restructured to confirm-before-generate (`self.phase`, `self.confirmed_test_cases`, `handle_approve` phase-dispatch, `process` rewritten to generate from `self.confirmed_test_cases`). 13.3 does not touch the lifecycle, but the test scaffold must set `agent.phase = "script_review"` so `handle_approve` dispatches to the existing script-review branch.
3. **12.2/12.3 `TestCase` fields** (`objective`, `test_data`, `source_requirement_id`, `source_requirement_name`, `source_url`, `feature_area`, `warnings`; plus 12.3's `confidence`/`confidence_level`). 13.3's source-step attribution reads `test_case.steps` / `test_case.expected_results` (present on the **pre-12.2** baseline already — [models.py:280-287](src/ai_qa/models.py:280)); it does **not** require the 12.2 fields, so it degrades gracefully. Any optional field read uses `getattr(tc, "...", None)`.

If 13.2 / 13.1 / Epic 12 are unmerged when you start, this story is **blocked**: there is no `warnings` channel to extend and no script-generation engine in its 13.2 shape. Flag and stop rather than re-implementing upstream.

---

## Scope decisions (CONFIRMED — Thuong locked all four defaults 2026-06-13)

Chosen from the code + ACs + planning docs + the 12.3 precedent and the 13.2 sibling, and **confirmed by Thuong** ("hãy dùng hết default", 2026-06-13). The four formerly-open questions are now resolved decisions (full list under "Confirmed decisions" at the end of this file). No pending input — the dev agent implements exactly as written.

- **This is a backend specialization story (mirror 12.3 / extend 13.2).** The work is: (a) **strengthen the prompts** with brittle-selector flagging + ambiguous-assertion warning rules (on top of 13.2's no-unsafe-inference rule and selector-priority block), (b) add **deterministic detectors** in the engine — `_detect_brittle_selectors(...)` and `_detect_assertion_gaps(...)` — that append categorized, source-attributed strings to the **same** `warnings` list 13.2 created, and (c) ensure those warnings flow through the existing channel (`StageResult.warnings` → `GeneratedScript.warnings` → `review_data["warnings"]`). **No new frontend component** — the side-by-side review card that renders warnings is **Story 13.5**. **No new model field / no migration** — warnings stay a `list[str]` (Saved Q#2 CONFIRMED).
- **Detection is HYBRID: prompt-driven behavior + deterministic engine scan (Saved Q#1 CONFIRMED = hybrid).** This is the exact analog of how 12.2 built the prompt-driven warning behavior and 12.3 added the **deterministic** scoring/forcing layer. The prompt asks the LLM to emit a `# REVIEW:` marker when it must fall back to a brittle selector or cannot map an expected result (behavioral half, builds on 13.2). The deterministic scanner **independently** flags brittle selectors and assertion-coverage gaps in the finished script — so a brittle selector is flagged **even if the LLM forgot to comment it**. Deterministic detection is authoritative for AC1/AC2 flagging; the LLM marker supplies the human-readable "why" and (via the `# Step N:` comment) the step attribution.
- **Confidence stays as-is (Saved Q#4 CONFIRMED = do NOT touch `_calculate_confidence`).** [`_calculate_confidence`](src/ai_qa/pipelines/script_generator.py:494) already deterministically rewards `data-testid`/role/text and penalizes XPath (>2) / raw CSS (>3). 13.3 **reuses the same detection regexes for flagging** but does **not** change the confidence number — flags are an **independent advisory surface** (no double-counting). This matches 13.2's explicit fence ("AC3 warnings are independent of the confidence number; do not fold warning counts into the score"). (12.3 forced low confidence on warnings for *Mary*; Sarah's confidence is Epic-5 and intentionally left alone — see Boundary fences.)
- **Brittle-selector flagging is per-occurrence, not threshold-gated (Saved Q#3 CONFIRMED = flag each occurrence).** AC1 says "brittle selectors are flagged for review" — every XPath and every raw-CSS/structural locator gets a warning (one warning per brittle selector, with step attribution). This is distinct from the confidence *penalty*, which keeps its existing thresholds (>2 XPath, >3 CSS). Flagging ≠ penalizing.
- **Warnings remain a flat `list[str]` with a stable category + source prefix (Saved Q#2 CONFIRMED = flat).** Reuse 13.2's `list[str]` channel. Each 13.3 warning is one human-readable string with a leading category tag and the source ref baked in, e.g. `"Brittle selector (Step 3): page.locator(\"xpath=//button\") — prefer get_by_test_id/get_by_role/get_by_label"` and `"Assertion gap: only 1 of 3 expected results mapped to expect() — review expected result(s) for missing/ambiguous assertions"`. **No structured warning objects, no new model field** (13.5 renders strings; a category taxonomy is premature until the renderer exists). 13.2 explicitly left this open ("avoid hardcoding that would block 13.3 from adding categorized warnings later") — the category-prefix convention satisfies that without a model change.
- **Selector-stability *enforcement* beyond flagging is out of scope.** 13.3 does not rewrite the LLM's selectors, re-query the DOM, or block on brittle selectors — it **flags** them for human review (mandatory-review principle). Auto-fixing selectors would be a future enhancement, not this story.
- **Feedback-driven regeneration is Story 13.7; SSO/secret rules are 13.4; the review UI is 13.5; artifact-save metadata is 13.8.** All new detection lives in the **base** engine path, so it benefits both first-pass and regeneration automatically (no feedback wiring here).

## What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| Selector-priority block (`data-testid` > role > text > label > placeholder > CSS > XPath) in the live prompt | [prompts/script_generation.py:32-39](src/ai_qa/prompts/script_generation.py:32) | ✅ **keep** — AC1 priority order already present; 13.3 **adds** the brittle-fallback flagging rule below it |
| Assertion-mapping block (expected result → `expect(...)`) in the live prompt | [prompts/script_generation.py:48-54](src/ai_qa/prompts/script_generation.py:48) | ✅ **keep** — AC2 mapping already present; 13.3 **adds** the "unsupported/ambiguous → `# REVIEW:` marker, never invent" rule |
| `SELECTOR_GUIDANCE_PROMPT` / `ASSERTION_MAPPING_GUIDE` reference prompts (not used by the live engine) | [prompts/script_generation.py:112-132](src/ai_qa/prompts/script_generation.py:112), [:176-208](src/ai_qa/prompts/script_generation.py:176) | ✅ reference only — update for consistency if you touch them; the live engine uses `SCRIPT_GENERATION_PROMPT` + `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT` |
| `# TODO:` / `# REVIEW:` inline-marker convention + `_extract_review_warnings(script)` scan | added by **13.2** in [script_generator.py](src/ai_qa/pipelines/script_generator.py) `_generate_single_script` | ⚠️ **reuse** — 13.3's deterministic detectors append to the **same** `warnings` list `_extract_review_warnings` populates; the LLM brittle/ambiguity markers are caught by it automatically |
| `warnings: list[str]` on `GeneratedScript`; `StageResult.warnings` aggregation; `review_data["warnings"]` | `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) + `generate` warnings aggregation ([script_generator.py:98-99](src/ai_qa/pipelines/script_generator.py:98)) + `review_data` ([sarah.py:714-725](src/ai_qa/agents/sarah.py:714)) — all added by **13.2** | ⚠️ **reuse the entire channel** — 13.3 produces more warnings into the same list; no new field, no new payload key |
| Deterministic XPath/CSS detection (for the confidence penalty) | [`_calculate_confidence`](src/ai_qa/pipelines/script_generator.py:494) — XPath count [:537](src/ai_qa/pipelines/script_generator.py:537), CSS regex `page\.locator\(["\']([^"\']+)["\']\)` [:542](src/ai_qa/pipelines/script_generator.py:542) | ✅ **reuse the regexes/heuristics for flagging** — extract or share with the new detectors; **do NOT change the confidence number** (Saved Q#4 default) |
| Stable-selector recognizers (`get_by_test_id`/`get_by_role`/`get_by_label`/`get_by_text`/`get_by_placeholder`/`get_by_alt_text`/`get_by_title`) | implied by the priority block + the confidence bonuses ([:513-517](src/ai_qa/pipelines/script_generator.py:513)) | ✅ the brittle-detector's allow-list (anything NOT one of these inside a `page.locator(...)` is a candidate brittle selector) |
| `test_case.steps` (with `.number`) + `test_case.expected_results` for source attribution | [models.py:244-287](src/ai_qa/models.py:244) (`TestCaseStep.number` [:257](src/ai_qa/models.py:257), `expected_results` [:283](src/ai_qa/models.py:283)) | ✅ **read** — assertion-gap warning compares `len(expected_results)` vs `expect(` count; step attribution uses the nearest `# Step N:` comment (13.2) |
| Per-step `# Step N:` comments emitted by the prompt | added/strengthened by **13.2** Task 2 ([prompts/script_generation.py:56-61](src/ai_qa/prompts/script_generation.py:56)) | ✅ **rely on** for AC3 brittle-selector step attribution (best-effort; fall back to no step ref if absent) |
| LLM retry, LangChain string/list normalization | [script_generator.py:231-235](src/ai_qa/pipelines/script_generator.py:231), [:270-291](src/ai_qa/pipelines/script_generator.py:270) | ✅ **keep** — detectors run on the already-normalized `script_content` string |

---

## Tasks / Subtasks

- [x] **Task 0 — Confirm prerequisites (BLOCKING gate)**
  - [x] Verify the live tree contains 13.2's `warnings` channel: `GeneratedScript.warnings` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)), `_extract_review_warnings` in `ScriptGenerator`, the populated `"warnings"` key in `_generate_single_script`'s return, and `"warnings"` in `_present_current_script_for_review`'s `review_data`. Verify 13.1's `self.phase`/`confirmed_test_cases` lifecycle and that `process` generates from `self.confirmed_test_cases`. If **any** is missing, 13.2/13.1/Epic 12 is unmerged → **flag and stop** (do not re-implement upstream). Record the verification result in Completion Notes (per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md)).

- [x] **Task 1 — Strengthen the prompts: brittle-selector flagging + ambiguous-assertion warnings (AC1, AC2, AC3)**
  - [x] In [prompts/script_generation.py](src/ai_qa/prompts/script_generation.py), in `SCRIPT_GENERATION_PROMPT` ([:20-73](src/ai_qa/prompts/script_generation.py:20)) **below** the existing selector-priority block ([:32-39](src/ai_qa/prompts/script_generation.py:32)), add a **brittle-selector rule**: "Prefer the stable selectors above. If — and only if — no stable selector is derivable from the test case, you may fall back to a CSS or XPath locator, but you MUST add an inline `# REVIEW:` comment on that line naming the test step and stating the selector is brittle and which stable selector would be preferred (e.g. `# REVIEW: Step 3 brittle selector — needs data-testid/role`). Never silently emit a brittle selector."
  - [x] **Below** the assertion-mapping block ([:48-54](src/ai_qa/prompts/script_generation.py:48)), add an **assertion-warning rule**: "Map every expected result to a concrete `expect(...)` assertion where the outcome is observable. If an expected result is ambiguous, unsupported, or has no checkable outcome, do NOT invent an assertion — add an inline `# REVIEW:` comment naming the expected result and what is ambiguous." (Reuses 13.2's `# REVIEW:` token — do **not** introduce a new marker token.)
  - [x] Reinforce the **step-comment** instruction so the `# Step N:` comments 13.2 added are reliably present (AC3 attribution depends on them): "Precede each mapped step's actions with a `# Step N: <action>` comment so warnings can be traced to the source step."
  - [x] Apply the **same** brittle-flagging + assertion-warning rules to `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT` ([:134-161](src/ai_qa/prompts/script_generation.py:134)) — its existing "Low confidence (<0.5): Add comment, use alternative selector" line ([:157](src/ai_qa/prompts/script_generation.py:157)) should be aligned to emit `# REVIEW:` for brittle fallbacks too, so both paths produce the same marker tokens.
  - [x] Keep `SCRIPT_GENERATION_SYSTEM_PROMPT` / `VISION_SCRIPT_GENERATION_SYSTEM_PROMPT` consistent (the "prefer stable selectors" principle already exists at [:13](src/ai_qa/prompts/script_generation.py:13)). Optionally fold the new flagging guidance into the auxiliary `SELECTOR_GUIDANCE_PROMPT`/`ASSERTION_MAPPING_GUIDE` for reference parity. Keep `__all__` ([:210-218](src/ai_qa/prompts/script_generation.py:210)) in sync if you add an exported constant (avoid `Literal`-default pitfalls — type any new module constant).

- [x] **Task 2 — Deterministic brittle-selector detector in the engine (AC1, AC3)**
  - [x] Add `_detect_brittle_selectors(self, script_content: str) -> list[str]` to `ScriptGenerator`. Walk the script **line by line**, tracking the nearest preceding `# Step N:` comment (regex `^\s*#\s*Step\s+(\d+)\b` — capture N). For each line, flag:
    - **XPath:** any `xpath=` inside a `page.locator(...)` (or `.locator("xpath=...")`).
    - **Raw CSS / structural:** a `page.locator("...")` whose argument is **not** `xpath=` and is **not** one of the stable `get_by_*` recognizers — i.e. CSS selectors (`#id`, `.class`, tag, attribute), and structural/positional patterns (`:nth-child`, `>`, descendant chains, `[n]`).
  - [x] Each flagged occurrence → one warning string: `f"Brittle selector (Step {n}): {snippet} — prefer get_by_test_id/get_by_role/get_by_label/get_by_text"` (omit the `(Step {n})` segment if no preceding `# Step N:` comment — best-effort attribution per AC3). Keep the snippet short (the matched locator call, truncated). **Reuse the same XPath/CSS detection regexes that `_calculate_confidence` uses** ([:537](src/ai_qa/pipelines/script_generator.py:537), [:542](src/ai_qa/pipelines/script_generator.py:542)) — factor a shared module-level helper or constant if it reads cleaner, but **do not change `_calculate_confidence`'s scoring**.
  - [x] **Allow-list discipline:** lines using only `get_by_test_id`/`get_by_role`/`get_by_label`/`get_by_text`/`get_by_placeholder`/`get_by_alt_text`/`get_by_title` produce **no** warning (those are the stable selectors AC1 prefers). Chained stable+brittle (`page.get_by_test_id("form").locator(".btn")`) → flag the brittle part.

- [x] **Task 3 — Deterministic assertion-gap detector in the engine (AC2, AC3)**
  - [x] Add `_detect_assertion_gaps(self, script_content: str, test_case: TestCase) -> list[str]` to `ScriptGenerator`. Compute `expected_count = len(test_case.expected_results)` and `expect_count = script_content.count("expect(")`. If `expected_count > 0 and expect_count < expected_count`, emit one warning: `f"Assertion gap: only {expect_count} of {expected_count} expected result(s) mapped to expect() assertions — review for missing/ambiguous assertions"`. (Ties to "expected results" per AC3 at the aggregate level; per-result attribution comes from the LLM `# REVIEW:` markers caught by 13.2's `_extract_review_warnings`.)
  - [x] Do **not** attempt to semantically match which specific expected result is unmapped (that is LLM-judgment territory, deferred — same deterministic-only stance as 12.3). The coverage-gap warning + the LLM `# REVIEW:` markers together satisfy AC2's "remain visible as review warnings."

- [x] **Task 4 — Wire the detectors into the warning flow (AC1, AC2, AC3)**
  - [x] In `_generate_single_script` ([script_generator.py:182-214](src/ai_qa/pipelines/script_generator.py:182)), **after** 13.2's `_extract_review_warnings(script_content)` runs and **after** `script_content` is validated, call both new detectors and merge their output into the per-case `"warnings"` list: `warnings = _extract_review_warnings(...) + self._detect_brittle_selectors(...) + self._detect_assertion_gaps(..., test_case)`. Return `{"success": True, ..., "warnings": warnings}` (replacing/extending 13.2's value at [:213](src/ai_qa/pipelines/script_generator.py:213)). `generate` already aggregates `result.get("warnings")` into `StageResult.warnings` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) — **no change there**.
  - [x] **Overlap handling (light):** the LLM may also emit a `# REVIEW:` marker on the same brittle selector that the deterministic detector flags → two warnings for one selector. This is acceptable (both are advisory). **Optional** light dedup: drop a deterministic brittle warning if an `_extract_review_warnings` entry already references the same line/step — but do **not** over-engineer; default is allow-both. Note the choice in Completion Notes.
  - [x] Confirm the warnings already flow downstream via 13.2's wiring: `StageResult.warnings` → Sarah `_generate_scripts` reads per-case warnings onto `GeneratedScript.warnings` → `_present_current_script_for_review` puts them in `review_data["warnings"]`. **13.3 adds nothing new to `sarah.py`** beyond confirming the flow (the warnings are richer, but the plumbing is 13.2's). If 13.2's plumbing only populated `StageResult.warnings` (aggregate) and not per-`GeneratedScript.warnings`, reconcile so per-script warnings are populated (this is the AC3 surface the review UI needs).

- [x] **Task 5 — Backend tests (AC1, AC2, AC3)**
  - [x] **Prompt** ([tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py)): assert `SCRIPT_GENERATION_PROMPT` (and the vision variant) contain the brittle-selector flagging rule + the ambiguous-assertion warning rule + the `# Step N:` comment instruction, and still forbid inventing selectors/assertions when unspecified. Guards AC1/AC2 against prompt regression.
  - [x] **Brittle-selector detector** (AC1, AC3): feed `_detect_brittle_selectors` a script with `# Step 2:` then `page.locator("xpath=//button")` and a raw `page.locator(".submit-btn")`, assert two warnings, each prefixed `Brittle selector` and the XPath one carrying `(Step 2)`. Assert a script using only `get_by_test_id`/`get_by_role`/`get_by_label`/`get_by_text` yields **zero** brittle warnings (no false positives). Assert a brittle selector with no preceding `# Step N:` is still flagged (omits the step ref).
  - [x] **Assertion-gap detector** (AC2, AC3): a `TestCase` with 3 `expected_results` and a script with 1 `expect(` → one `Assertion gap: only 1 of 3` warning; a script with `expect_count >= expected_count` → no gap warning; `expected_results == []` → no gap warning.
  - [x] **End-to-end through the engine** (AC1/AC2): mock the LLM (`_call_llm`) to return a script containing both a brittle XPath and fewer assertions than expected results; assert the detected warnings appear in `StageResult.warnings` from `generate(...)`, and (via Sarah) on `GeneratedScript.warnings` and in the `review_data["warnings"]` payload of `_present_current_script_for_review`. Set `agent.phase = "script_review"` (13.1) in the Sarah test.
  - [x] **Confidence untouched** (Saved Q#4 default): assert the existing confidence tests ([test_script_generator.py:273-328](tests/pipelines/test_script_generator.py:273)) still pass unchanged — `_calculate_confidence` behavior must not change. (Regression guard for the "do not double-count" decision.)
  - [x] **Back-compat:** a clean script (all stable selectors, full assertion coverage, no markers) yields **empty** warnings — existing `test_generate_single_test_case` / `test_generate_multiple_test_cases` still pass.
  - [x] If shared fixtures break, fix [tests/conftest.py](tests/conftest.py) **centrally** ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test.

- [x] **Task 6 — Verify (no migration)**
  - [x] Backend: `uv run pytest --no-cov` (whole suite — the coverage gate fails on subset runs; see [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). Mypy gate: `uv run mypy src`. Code must also pass **Pyrefly** — narrow `Any`/`Optional` before use (`test_case.expected_results` is a `list[str]`; the per-case dict `result.get("warnings")` is `Any` → coerce to `list[str]` before merging; compiled `re` matches are `Match | None` → guard). No redundant casts/conversions; type any new marker/category module constant (avoid the `Literal`-default pitfall). Note the file already carries `# mypy: disable-error-code="misc"` at the top of [script_generator.py:1](src/ai_qa/pipelines/script_generator.py:1) — keep new code clean regardless.
  - [x] Confirm **no Alembic migration** is required (warnings stay a `list[str]` on the in-memory `GeneratedScript`; the script persists as text artifact content; `TestCase` is a JSON model). State explicitly in Completion Notes.
  - [x] Frontend: **no component change in 13.3.** Run `npm run typecheck` only to confirm nothing broke — the enriched `review_data["warnings"]` is still untyped on the client until 13.5 (full-stack-sync handoff). Note the deferral in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/prompts/script_generation.py` — the prompts (most load-bearing AC1/AC2 change).**

- `SCRIPT_GENERATION_PROMPT` ([:20-73](src/ai_qa/prompts/script_generation.py:20)) already carries the **selector-priority block** ([:32-39](src/ai_qa/prompts/script_generation.py:32): `get_by_test_id` → `get_by_role` → `get_by_text` → `get_by_label` → `get_by_placeholder` → `page.locator` CSS → `xpath=` last resort) and the **assertion map** ([:48-54](src/ai_qa/prompts/script_generation.py:48)). 13.3 **keeps both** and appends the brittle-flagging + ambiguous-assertion rules below them. The "Output ONLY the Python test function code" line ([:73](src/ai_qa/prompts/script_generation.py:73)) was reconciled by 13.2 to permit inline `# TODO:`/`# REVIEW:` comments — confirm that reconciliation is present; the new `# REVIEW:` markers are valid Python comments and must not be suppressed.
- `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT` ([:134-161](src/ai_qa/prompts/script_generation.py:134)) has a confidence-tiered selector instruction ([:154-158](src/ai_qa/prompts/script_generation.py:154)) — align its low-confidence path to the same `# REVIEW:` marker convention.
- `SELECTOR_GUIDANCE_PROMPT` ([:112-132](src/ai_qa/prompts/script_generation.py:112)) and `ASSERTION_MAPPING_GUIDE` ([:176-208](src/ai_qa/prompts/script_generation.py:176)) are **auxiliary/reference** (not used by the live engine) — update for consistency only; the live engine uses the two prompts above.

**`src/ai_qa/pipelines/script_generator.py` — the engine (new deterministic detectors slot in here).**

- `_generate_single_script` ([:133-229](src/ai_qa/pipelines/script_generator.py:133)) is where 13.2 added `_extract_review_warnings` and the populated `"warnings"` return. 13.3 adds two more detectors after content validation ([after :206](src/ai_qa/pipelines/script_generator.py:206)) and merges their output into the same `"warnings"`.
- `generate` ([:64-131](src/ai_qa/pipelines/script_generator.py:64)) already aggregates per-case `result.get("warnings")` into `StageResult.warnings` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) — the channel is complete; 13.3 only produces more into it.
- `_calculate_confidence` ([:494-552](src/ai_qa/pipelines/script_generator.py:494)) already detects XPath ([:536-539](src/ai_qa/pipelines/script_generator.py:536)) and raw CSS ([:541-544](src/ai_qa/pipelines/script_generator.py:541)) for **penalties**. 13.3 reuses these detection patterns for **flagging** but **does not change the scoring** (Saved Q#4 default). Consider factoring the XPath/CSS regexes into shared module-level constants so the detector and the confidence calc don't drift — but if that risks touching the confidence number, prefer a separate (duplicated) regex in the detector and leave `_calculate_confidence` byte-for-byte unchanged.
- `_generate_script_header` ([:468-492](src/ai_qa/pipelines/script_generator.py:468)) is 13.2's rewrite target (durable traceability) — **do not touch** in 13.3.

**`src/ai_qa/agents/sarah.py` — the agent (13.3 only confirms the flow; 13.2 did the plumbing).**

- `GeneratedScript.warnings` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) — added by 13.2. 13.3 does not add fields.
- `_generate_scripts` ([:273-367](src/ai_qa/agents/sarah.py:273)) reads per-case warnings onto each `GeneratedScript` (13.2). Confirm the **per-script** warnings (not just `StageResult.warnings`) are populated — AC3's review UI ties warnings to a specific script/step, so they must live on `GeneratedScript.warnings`. If 13.2 only wired aggregate `StageResult.warnings`, reconcile here (read `result.data[0]["warnings"]` → `GeneratedScript(... warnings=...)`).
- `_present_current_script_for_review` ([:698-736](src/ai_qa/agents/sarah.py:698)) puts `"warnings"` in `review_data` (13.2). No change in 13.3.
- The per-item **script** review state machine (`handle_approve`/`handle_reject`/`handle_skip`/`handle_navigate`) is Epic-5 + 13.5+ territory — **do not touch**.

### The AC mechanic: specialize 13.2's channel, hybrid detection (most load-bearing change)

13.3 is to 13.2 what **12.3 is to 12.2**: 13.2 (like 12.2) built the generic warning channel + the "preserve ambiguity, never invent" behavior; 13.3 (like 12.3, which was **deterministic** — Thuong locked that 2026-06-12) adds the **specialized, deterministic** layer on top.

1. **Prompt-side (behavioral):** the LLM emits a `# REVIEW:` comment, in the test case's own words, at a brittle-selector fallback or an unmappable expected result — and never fabricates a selector/assertion. Builds on 13.2's marker convention; adds the *categories* (brittle selector, ambiguous assertion).
2. **Engine-side (deterministic, authoritative for flagging):** `_detect_brittle_selectors` and `_detect_assertion_gaps` scan the finished script and append categorized, source-attributed strings to the **same** `warnings` list — so AC1/AC2 hold **even if the LLM forgot to comment**. This is the 12.3-style deterministic guarantee.

Both halves write to **one** `warnings: list[str]` (13.2's channel). Keep the category prefix stable (`Brittle selector`, `Assertion gap`) and the step/expected-result reference inside the string (AC3) so the future 13.5 renderer can group/tie them without a model change.

### Source attribution (AC3) — best-effort, deterministic

- **Brittle-selector → step:** scan upward from the brittle line for the nearest `^\s*#\s*Step\s+(\d+)` comment (13.2 emits these). Include `(Step N)` in the warning. If none found, omit the step ref but still flag the selector. This is deterministic and tolerant — it does not require the LLM to cooperate beyond emitting the step comments 13.2 already mandates.
- **Assertion → expected result:** the aggregate `Assertion gap: only X of Y` warning ties to "expected results" collectively; the LLM `# REVIEW:` marker (caught by `_extract_review_warnings`) supplies the per-result detail. Do not attempt deterministic per-result matching (LLM-judgment, deferred — same stance as 12.3 deferring semantic scoring).

### Boundary fences (what 13.3 must NOT do)

- **Confidence (`_calculate_confidence`):** do **not** change the score, thresholds, or blending. 13.3's flags are independent of the confidence number (Saved Q#4 default = no double-count; matches 13.2's fence). The existing confidence tests must pass unchanged.
- **13.2 (the channel + no-unsafe-inference + header):** do not re-do `_extract_review_warnings`, the `# TODO:`/`# REVIEW:` token definition, or `_generate_script_header`. 13.3 **extends**, not rewrites.
- **13.4 (SSO/secrets):** do not add browser-session reuse. Do honor the no-invent rule (no fabricated credentials/URLs) — overlaps and is fine.
- **13.5 (review UX):** no frontend component, no syntax-highlight, no warning-rendering UI, no TS type. Only the backend `review_data["warnings"]` (already added by 13.2) carries the richer strings.
- **13.6/13.7 (edit/approve/regenerate):** do not wire feedback into the prompt; do not change the review state machine.
- **13.8 (artifact save):** do not expand save metadata or the save path (note: 13.2 flagged a `.spec.ts` save-fallback defect for 13.8 — leave it).
- **No selector auto-fixing / DOM re-querying / blocking on brittle selectors** — flag for human review only (mandatory-review principle).

### Architecture compliance (hard rules)

- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). 13.3 stays inside the generator/prompt; it does not touch storage.
- **Mandatory human review at every step — no auto-advance** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). Brittle selectors are **flagged for review**, never auto-corrected or auto-approved.
- **FR8 (stable selectors over fragile) / FR9 (map expected results into assertions)** ([prd.md:347-348](_bmad-output/planning-artifacts/prd.md:347)) — 13.3 is the story that operationalizes both into reviewer-visible flags. The PRD's Sarah scene ([prd.md:193](_bmad-output/planning-artifacts/prd.md:193)) explicitly names "a fragile selector … an incorrect assertion" as the things the reviewer catches — 13.3 surfaces exactly those.
- **Sarah model needs** ([architecture.md:1163-1167](_bmad-output/planning-artifacts/architecture.md:1163)): framework-aware, runnable output — the prompt rewrite reinforces stable selectors and makes brittle fallbacks explicit, not silent.
- **No credential/secret leakage** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the `warnings`/`review_data` payload carries only category tags, selector snippets, step numbers, and counts — never secrets or config dicts. The leak-canary convention applies (selector snippets are from generated code, not user secrets — confirm no URL/credential ends up in a snippet; the no-invent rule already forbids fabricating those).
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the enriched `review_data["warnings"]` is **untyped on the client** until 13.5 builds the script-review panel + TS type. Flag this handoff in Completion Notes.
- **Artifacts project-scoped** under `projects/{project_id}/test_scripts/` ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)) — relevant to the save path (13.8), not generation.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Must also pass **Pyrefly** — narrow `Optional`/`Any` before use (`result.get("warnings")` is `Any` → coerce to `list[str]`; `re` matches are `Match | None`); no redundant casts/conversions; type any new module constant (avoid `Literal`-default pitfalls). `pytest.raises(Exception)` prohibited — specific exception type + `match=`. The generator path is a **sync** LLM call inside async (no async-SQLAlchemy concerns). Compile `re` patterns at module level for the line scan.
- **Prompt strings are Python literals**, not markdown-linted; this story file follows the markdown rules (lists `-`, MD036 real headings, MD060 table spacing).
- **Config:** no new `AppSettings` field needed — brittle/assertion detection is deterministic with no tunable knob (the existing `confidence_threshold` is for the confidence number, untouched here).
- **No new packages. No Alembic migration.**

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/prompts/script_generation.py` (brittle-flagging + assertion-warning prompt rules), `src/ai_qa/pipelines/script_generator.py` (two new deterministic detectors + merge into the per-case warnings), possibly a one-line confirm/reconcile in `src/ai_qa/agents/sarah.py` (per-`GeneratedScript.warnings` population, only if 13.2 left it aggregate-only), `tests/pipelines/test_script_generator.py` (prompt + detector tests + confidence-unchanged regression), possibly `tests/test_agents/test_sarah.py` (warnings-on-`GeneratedScript` surfacing), possibly `tests/conftest.py`.
- **No new files required** (the detectors live in `script_generator.py`). **No frontend files** (13.5 owns the script-review component + TS type).
- **No backend route/schema/REST changes** — the richer `review_data["warnings"]` rides the existing WebSocket `send_message` metadata channel (added by 13.2).

### Testing standards summary

- Backend: pytest. `ScriptGenerator` tests patch `_get_llm_client` (or `ai_qa.pipelines.script_generator.LLMClient`) and set `mock_response.content`; the new detectors are **pure functions** — test them directly with literal script strings (no LLM needed). Sarah tests patch `ai_qa.agents.sarah.ScriptGenerator` (+ `PipelineArtifactAdapter`) and set the mocked `generate` return so `result.data[0]["warnings"]` carries the detected strings; set `agent.phase = "script_review"` (13.1). Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; prior-epic baseline = 1098 passed). Mypy gate is `src` only.
- Frontend: no Vitest/Playwright change in 13.3 (deferred to 13.5). Only `npm run typecheck` to confirm no breakage. LLM-driven generation is not E2E-reproducible without a provider key, and the new detectors are deterministic units — E2E is **not** the right layer for AC1/AC2 (covered by backend unit tests).

### Previous-story intelligence

- **Story 12.3 (Mary confidence-scoring)** — the **direct structural analog**. Same shape: a **deterministic** specialization layer added on top of a sibling's generic warning channel (12.2). 12.3's confidence-method fork was **resolved to DETERMINISTIC** by Thuong (2026-06-12; no LLM judge, semantic scoring deferred) — 13.3 follows the same deterministic stance for brittle-selector/assertion-gap detection. **Key difference:** 12.3 produced a confidence *number* (and forced low confidence on warnings); 13.3 produces *categorized warning strings* and explicitly leaves Sarah's confidence number alone (Saved Q#4 default).
- **Story 13.2 (Sarah generation engine — immediate prerequisite)** — built the `warnings: list[str]` channel, `_extract_review_warnings`, the `# TODO:`/`# REVIEW:` marker convention, the no-unsafe-inference rule, and the durable header. It **explicitly reserved** brittle-selector flagging + assertion-mapping warnings for 13.3 and said "keep the marker tokens simple and stable … a future story (13.3) will *add* categories … but should reuse the same channel rather than invent a parallel one." 13.3 honors that: same channel, category prefix, no new token, no new field.
- **Story 13.1 (Sarah input selection)** — restructured Sarah's lifecycle (confirm-before-generate). 13.3 does not touch it; tests set `agent.phase = "script_review"`.
- **Epic 5 (Sarah, `done`)** — built `ScriptGenerator`/`VisionLocator`, the prompts, the per-item script review loop, and the existing confidence heuristic (`_calculate_confidence`'s XPath/CSS detection is the reuse seam for 13.3's flagging). 13.3 refines the prompt + adds detectors; it does not touch the review loop or vision plumbing.
- **Stories 13.4/13.5/13.7/13.8** — the explicit fences above. 13.5 builds the review UI that renders these warnings (the full-stack-sync handoff target); 13.4 adds SSO/secret rules; 13.7 wires feedback regeneration; 13.8 saves the artifact + metadata.

### Git intelligence (recent work patterns)

Recent commits (`2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`) are Epic 10/11. **Epic 12 (12.1–12.5), Story 13.1, and Story 13.2 are NOT implemented** — the live `sarah.py`/`script_generator.py`/`prompts/script_generation.py`/`TestCase` are pre-12.1/pre-13.1/pre-13.2. **13.3 is blocked until 13.2 lands** (it has no `warnings` channel to extend otherwise). Before relying on 13.2's `GeneratedScript.warnings`/`_extract_review_warnings`/marker convention, **verify they are present in the live tree** (Task 0); if unmerged, flag and stop rather than re-implementing upstream. Closest existing patterns to copy: [tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py) (engine test scaffold — confidence/filename/header/prompt; the confidence XPath/CSS tests show the detection patterns to reuse for flagging), [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py) (Sarah lifecycle scaffold), and the **12.3 story** (the deterministic-specialization-on-top-of-a-sibling-channel pattern).

### Sibling-story note (reusability)

13.3 reuses (does **not** fork) the review-marker channel 13.2 established: in-script `# TODO:`/`# REVIEW:` + `warnings: list[str]` on `GeneratedScript`/`StageResult`/`review_data`. The category-prefix convention (`Brittle selector …`, `Assertion gap …`) keeps the channel a flat `list[str]` while making warnings groupable by the future 13.5 renderer — no model change, no migration. Keep the detectors pure and prompt-agnostic so any later refinement (categorized objects, per-result attribution) can layer on without rewriting the scan. If 13.5 ever needs structured warnings, it can parse the stable prefixes or 13.5 itself can introduce the structured field then — do **not** pre-build it here.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-13.3] — ACs (lines 1302-1322); Epic 13 intro + FRs (1253-1257); sibling 13.2 generation engine (1281-1300), 13.4 SSO (1324-1343), 13.5 review UX with warnings-visible AC (1345-1365), 13.8 script save (1411-1430)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR8 stable selectors over fragile (347), FR9 map expected results into assertions (348); pipeline notes on assertions/selectors (315-316); Sarah review scene naming "fragile selector … incorrect assertion" (193)
- [Source: _bmad-output/planning-artifacts/architecture.md] — Sarah flow `script_generator.py → … → test_scripts/` (824-828), Sarah model needs (1163-1167), no-direct-storage (518, 533), no-auto-advance / mandatory review (271-272), project-scoped artifacts (280)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — mandatory review gate (188); Sarah/script step UX
- [Source: src/ai_qa/prompts/script_generation.py] — system prompt + stable-selector principle (7-18, esp. 13), main prompt (20-73), selector-priority block (32-39, **keep + extend**), assertion map (48-54, **keep + extend**), structure/step-comments (56-61), vision-assisted prompt + low-confidence selector line (134-161, esp. 154-158), auxiliary SELECTOR_GUIDANCE/ASSERTION_MAPPING (112-132, 176-208), `__all__` (210-218)
- [Source: src/ai_qa/pipelines/script_generator.py] — `generate` warnings aggregation (64-131, esp. 98-99), `_generate_single_script` warnings return (133-229, esp. 206-214), `_calculate_confidence` XPath/CSS detection to reuse for flagging — **do not change scoring** (494-552, esp. 536-544), `_generate_script_header` (468-492, 13.2's target, do not touch), `# mypy: disable-error-code` header (1)
- [Source: src/ai_qa/agents/sarah.py] — `GeneratedScript` (+`warnings` from 13.2; 26-37), `_generate_scripts` per-case construct (273-367, esp. 321-330), `_present_current_script_for_review` `review_data` incl. `warnings` from 13.2 (698-736, esp. 714-725), per-item script review loop (519-696, do NOT change)
- [Source: src/ai_qa/models.py:244-298] — `TestCase` (`expected_results` 283, `steps` 282, `filename` 291-298), `TestCaseStep.number` (257)
- [Source: tests/pipelines/test_script_generator.py] — confidence tests showing XPath/CSS detection patterns (273-328), header test (334-346), filename tests (217-270), LLM mock seam (360-369)
- [Source: tests/test_agents/test_sarah.py] — Sarah lifecycle test scaffold (patches ScriptGenerator + adapter)
- [Source: _bmad-output/implementation-artifacts/13-2-python-playwright-script-generation.md] — immediate prerequisite: the `warnings` channel, `_extract_review_warnings`, `# TODO:`/`# REVIEW:` convention, no-unsafe-inference, durable header; the explicit "13.3 specializes this channel" handoff
- [Source: _bmad-output/implementation-artifacts/12-3-confidence-scoring-for-generated-test-cases.md] — the deterministic-specialization analog (deterministic stance locked by Thuong; warnings-not-LLM-judge pattern)
- [Source: _bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md] — the lifecycle prerequisite (`self.phase`/`confirmed_test_cases`; set `phase="script_review"` in tests)
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional/Any, no redundant cast); no bare except; no `# type: ignore`; full-stack sync; security (no secrets in payloads/logs)

## Confirmed decisions (defaults locked by Thuong 2026-06-13 — "hãy dùng hết default")

All four formerly-open questions are resolved to their defaults. No pending input — implement exactly as stated.

1. **Detection method = hybrid (CONFIRMED).** The prompt asks the LLM to mark brittle fallbacks / ambiguous assertions with `# REVIEW:`, AND a deterministic scanner independently flags them so AC1/AC2 hold even if the LLM forgets. (Rejected: prompt-only — a forgotten flag = a silent brittle selector; deterministic-only — no per-result "why".) Mirrors 12.2-behavior + 12.3-deterministic.
2. **Warning shape = flat `list[str]` with a stable category + source prefix (CONFIRMED).** Reuses 13.2's channel; no new model field, no migration; 13.5 renders strings and can group by prefix. (Rejected: structured warning objects `{category, step, text}` — heavier, speculative until the 13.5 renderer exists.)
3. **Brittle-selector flagging granularity = per-occurrence (CONFIRMED).** Flag every brittle-selector occurrence (per-step), independent of the confidence thresholds. Flagging is advisory and distinct from the confidence penalty (which keeps its >2 XPath / >3 CSS thresholds). (Rejected: only flag beyond the confidence thresholds — would miss single brittle selectors.)
4. **Confidence interaction = `_calculate_confidence` untouched (CONFIRMED).** Flags are an independent advisory surface; no double-counting; matches 13.2's fence. (Rejected: folding brittle/assertion-gap flags into the confidence number à la 12.3 — Sarah's confidence is Epic-5 and 13.2 said don't touch it.)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- **Task 0 verified:** All 13.2 + 13.1 prerequisites confirmed present in the live tree: `GeneratedScript.warnings` (sarah.py:37), `_extract_review_warnings` (script_generator.py:441), per-case `"warnings"` key in `_generate_single_script` return (script_generator.py:209–216), `"warnings": script.warnings` in `review_data` (sarah.py:906), `self.phase` (sarah.py:81), `confirmed_test_cases` (sarah.py:83), `handle_approve` phase dispatch (sarah.py:693+).
- **Overlap handling:** LLM `# REVIEW:` markers and deterministic brittle-selector warnings may both appear for the same locator — allowed-both (two advisory warnings per brittle selector is acceptable; no light-dedup implemented as keeping it simple per the "do not over-engineer" guidance).
- **Module-level constants:** Three compiled `re` patterns added at module level in `script_generator.py`: `_STEP_COMMENT_RE`, `_XPATH_LOCATOR_RE`, `_CSS_LOCATOR_RE`. These are independent of (and do not change) `_calculate_confidence`'s inline patterns.
- **`_calculate_confidence` untouched:** Confidence scoring is byte-for-byte unchanged (Saved Q#4 confirmed). Flags are an independent advisory surface. Confirmed by the `test_confidence_unchanged_by_13_3_detectors` test which passes.
- **No Alembic migration required:** `warnings` stays `list[str]` on the in-memory `GeneratedScript`; the script persists as text artifact content; `TestCase` is a JSON model. No DB schema change.
- **No sarah.py changes:** 13.2's wiring (`script_data.get("warnings") → GeneratedScript.warnings → review_data["warnings"]`) is complete and richer warnings flow through automatically. Confirmed by the new Sarah E2E tests.
- **Full-stack sync deferred to 13.5:** The enriched `review_data["warnings"]` is still untyped on the client. The frontend typecheck passes (`npm run typecheck` → clean). The review UI that renders categorized warnings is 13.5's scope.
- **Pre-existing test updated:** `test_generate_single_script_populates_warnings` now checks for the TODO warning by content rather than exact count, because 13.3's assertion-gap detector also fires on the `sample_test_case` (which has 2 expected_results but the script has 0 `expect(` calls).
- **Test results:** 1302 passed, 0 failed (whole suite). Mypy: clean. Frontend typecheck: clean.

### File List

- src/ai_qa/prompts/script_generation.py
- src/ai_qa/pipelines/script_generator.py
- tests/pipelines/test_script_generator.py
- tests/test_agents/test_sarah.py
- _bmad-output/implementation-artifacts/13-3-stable-selector-and-assertion-mapping.md
- _bmad-output/implementation-artifacts/sprint-status.yaml


## Change Log

| Date | Change |
| --- | --- |
| 2026-06-16 | Implemented Story 13.3: brittle-selector flagging + assertion-gap detection. Added  and  to ScriptGenerator; strengthened SCRIPT_GENERATION_PROMPT and VISION_ASSISTED_SCRIPT_GENERATION_PROMPT with brittle-fallback and ambiguous-assertion rules; wired detectors into ; added 25 new tests (prompt guards, detector units, E2E, Sarah warnings flow). 1302 passed, mypy clean. |
