---
baseline_commit: 2a1f170
---

# Story 13.2: Python Playwright Script Generation

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Sarah to generate Python Playwright scripts from approved test cases,
so that each approved test case can become an executable browser automation file.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.2](_bmad-output/planning-artifacts/epics.md) (lines 1281-1300), expanded with implementation defaults (see "Scope decisions" â€” **all four defaults CONFIRMED by Thuong 2026-06-13** ("dÃ¹ng toÃ n bá»™ default"); no pending input remains). This is the **script-generation analog of Story 12.2** (Mary's browser-automation-oriented test-case generation): a backend **generation-engine** story that rewrites the prompt and the engine to (a) produce complete, convention-following output, (b) stamp durable source traceability, and (c) **preserve missing details as explicit warnings/TODO markers instead of inventing unsafe behavior**.

### AC1 â€” One Python Playwright script per approved test case, project-standard conventions

- **Given** approved test cases are selected (the `self.confirmed_test_cases` set produced by Story 13.1)
- **When** Sarah generates scripts
- **Then** exactly **one** Python Playwright script is generated **per approved test case** (one-to-one; no batching multiple cases into one file)
- **And** generated scripts use project-standard Python and Playwright conventions: a `pytest`-style test function `def test_<name>(page: Page):`, `from playwright.sync_api import Page, expect`, `expect(...)` assertions (never bare `assert`), and a `test_<kebab>.py` filename derived from the test-case title (FR7)

### AC2 â€” Inspectable script: function, interactions, assertions, source traceability

- **Given** a generated script is created
- **When** its content is inspected
- **Then** it includes a **clear test function**, **browser/page interactions** (navigation, clicks, fills, etc.), **assertions** mapped from expected results, **and comments or metadata that link back to the source test case** (the docstring header references the originating test case by title and durable source reference â€” NOT a stale `workspace/testcases/â€¦json` path; per-step comments reference the source step)

### AC3 â€” Missing details â†’ explicit warning / TODO marker, never invented unsafe behavior

- **Given** script generation encounters missing details
- **When** Sarah cannot safely infer an action, target, value, or outcome from the test case
- **Then** Sarah inserts an **explicit review warning or `# TODO:` / `# REVIEW:` marker** at that point describing what is missing, **rather than inventing unsafe behavior** (no fabricated URLs, credentials, selectors, or guessed assertions when the test case does not specify them)
- **And** those markers are **surfaced to the review layer** as per-script warnings (collected onto `GeneratedScript.warnings` and the `StageResult.warnings`), so the user sees them without reading every line

---

## âš ï¸ Sequencing dependency (READ FIRST â€” critical)

**Story 13.2 builds directly on Story 13.1, and Story 13.1 builds on Epic 12. As of `2a1f170`, NONE of these are implemented** â€” Stories 12.1â€“12.5 and 13.1 are all `ready-for-dev` and absent from the working tree. 13.2 **must** be implemented after 13.1 lands. Before starting, confirm the prerequisites are present in the live tree; **flag and stop** if missing â€” do NOT re-implement 13.1 or Epic 12 here.

What 13.2 assumes from upstream (verify present; reconcile against live code and note divergence in Completion Notes per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md)):

1. **13.1 (immediate prerequisite).** Sarah's lifecycle is restructured to **confirm-before-generate**: `self.phase`, `self.candidate_test_cases`, `self.confirmed_test_cases`, the `handle_approve` phase-dispatch, the `_check_preconditions` gate, the `load_approved_test_cases` adapter loader, and **`process(...)` rewritten to generate from `self.confirmed_test_cases`** (not `_load_test_cases()` over all cases). 13.2 **extends the 13.1 version** of `process`/`_generate_scripts`; do NOT re-do 13.1's selection gate. AC1's "approved test cases are selected" precondition is satisfied entirely by 13.1.
2. **12.2/12.3 `TestCase` fields** (`objective`, `test_data`, `source_requirement_id`, `source_requirement_name`, `source_url`, `feature_area`, `warnings`; plus 12.3's `confidence`/`confidence_level`). 13.2's traceability header reads these via `getattr(tc, "...", None)` so it **degrades gracefully** on the pre-12.2 `TestCase` ([models.py:265-298](src/ai_qa/models.py:265) has only `title`/`preconditions`/`steps`/`expected_results`/`automation_hints`/`tags` + `filename`).
3. **12.5 (producer of approved test cases).** Without it `load_approved_test_cases()` is empty and there is nothing to generate from â€” but that is 13.1's AC3 block path, not 13.2's concern.

If Epic 12 / 13.1 are unmerged when you start, this story is **blocked**: there are no approved test cases to consume and no `confirmed_test_cases` plumbing to extend. Flag and stop.

---

## Scope decisions (CONFIRMED â€” Thuong locked all four defaults 2026-06-13)

Chosen from the code + ACs + planning docs + the 12.2 precedent and **confirmed by Thuong** ("dÃ¹ng toÃ n bá»™ default", 2026-06-13). The four formerly-open questions are now resolved decisions (full list under "Confirmed decisions" at the end). No pending input â€” the dev agent implements exactly as written.

- **This is a backend generation-engine story (mirror 12.2).** The work is: rewrite the script-generation **prompts** (no-unsafe-inference + TODO/REVIEW markers + strengthened traceability), add a **`warnings` field to `GeneratedScript`**, add **marker detection** in the engine to surface those warnings, and rewrite **`_generate_script_header`** for durable source traceability. **No new frontend component** is built here â€” the side-by-side script review card (with syntax highlighting + warning display) is **Story 13.5**. The new `warnings` ride the existing `review_data` `metadata` channel automatically; it is currently unconsumed on the client (no Sarah script-review UI exists yet â€” see [13.1 Dev Notes "Frontend reality"](_bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md)).
- **Confidence stays as-is.** Do **not** expand `_calculate_confidence` ([script_generator.py:494-552](src/ai_qa/pipelines/script_generator.py:494)). It already rewards stable selectors / assertions and penalizes XPath/raw-CSS. AC3 warnings are independent of the confidence number; do not fold warning counts into the score here.
- **Selector-stability flagging and assertion-mapping warnings are Story 13.3, not 13.2.** The existing prompt already carries selector-priority guidance (`data-testid` > role > text > label > CSS > XPath) and an assertion map â€” **keep them**. 13.2 establishes the **warning channel + the "no unsafe inference" principle + TODO-marker convention**; **13.3 specializes** it to *brittle-selector flagging* and *ambiguous-expected-result warnings tied to source steps* (exactly as 12.2 built the `warnings` channel and 12.3 specialized it). Scope 13.2's AC3 warnings to **genuinely-missing detail / unsafe-to-infer actions** (e.g. a step with no concrete control or value, an expected result with no checkable outcome) â€” not to "this selector could be more stable" (that's 13.3).
- **Feedback-driven regeneration is Story 13.7.** `_regenerate_current_script` ([sarah.py:373-454](src/ai_qa/agents/sarah.py:373)) explicitly does NOT pass feedback into the prompt ([:412-413](src/ai_qa/agents/sarah.py:412)). Leave that gap for 13.7; do **not** wire feedback into the prompt here. The new no-unsafe-inference behavior lives in the **base** prompt, so it benefits both first-pass and regeneration automatically.
- **SSO / browser session reuse + secret-leak prevention are Story 13.4.** 13.2 must not *introduce* hardcoded credentials (the no-invent rule forbids fabricating any secret/URL), but building SSO/session support is out of scope.
- **Script artifact-save metadata is Story 13.8.** Do **not** expand `_write_approved_scripts_metadata` ([sarah.py:738-757](src/ai_qa/agents/sarah.py:738)) or the save path. (Noted defect there â€” see Saved Question #4.)
- **No Alembic migration.** `GeneratedScript` is an in-memory Pydantic model; the script is saved as **text** artifact content. No DB table changes. Confirm explicitly in Completion Notes.

## What ALREADY EXISTS (reuse â€” do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| One-script-per-test-case loop (Sarah iterates per case, calls `generate(test_cases=[tc])`) | [sarah.py:293-310](src/ai_qa/agents/sarah.py:293) | âœ… AC1 one-to-one already structural â€” **keep**; generate from `self.confirmed_test_cases` (wired by 13.1) |
| `ScriptGenerator.generate` â†’ per-case `_generate_single_script` (LLM or vision-assisted) | [script_generator.py:64-229](src/ai_qa/pipelines/script_generator.py:64) | âœ… engine exists â€” **extend** with marker detection; do not rewrite the loop |
| `pytest` test-function signature `def test_<name>(page: Page)` + `expect()`-only assertions enforced **by the prompt**; the `import pytest` / `from playwright.sync_api import Page, expect` lines are emitted **by `_generate_script_header`** ([script_generator.py:489-490](src/ai_qa/pipelines/script_generator.py:489)), not the prompt | [prompts/script_generation.py:7-73](src/ai_qa/prompts/script_generation.py:7) | âœ… AC1 conventions present â€” **keep**, add AC3 rules on top |
| `test_<kebab>.py` filename derivation from title (FR7) | [script_generator.py:436-466](src/ai_qa/pipelines/script_generator.py:436) | âœ… done â€” Python `.py`, Unicode-safe, length-capped; **keep** |
| Script header docstring (title, source, timestamp, model) + `import pytest` / `from playwright.sync_api import Page, expect` | [script_generator.py:468-492](src/ai_qa/pipelines/script_generator.py:468) | âš ï¸ **rewrite** for AC2 â€” the `Source: workspace/testcases/{name}.json` line ([:484](src/ai_qa/pipelines/script_generator.py:484)) is a stale/false path; replace with durable source-test-case traceability |
| Selector-priority guidance + assertion map in prompt | [prompts/script_generation.py:32-73](src/ai_qa/prompts/script_generation.py:32), [:176-208](src/ai_qa/prompts/script_generation.py:176) | âœ… **keep** â€” refinement (brittle flagging) is 13.3 |
| Deterministic confidence (`data-testid`/role bonus, XPath/CSS penalty) | [script_generator.py:494-552](src/ai_qa/pipelines/script_generator.py:494) | âœ… **do not touch** (analog of 12.3 owning confidence) |
| `GeneratedScript` review DTO (`test_case`, `script_content`, `file_path`, `confidence`, `approved`, `error_message`) | [sarah.py:26-37](src/ai_qa/agents/sarah.py:26) | âš ï¸ **add `warnings: list[str] = []`** (AC3) â€” analog of 12.2 adding `warnings` to `TestCase` |
| `_generate_single_script` returns a dict carrying `"warnings": []` (always empty today) | [script_generator.py:208-214](src/ai_qa/pipelines/script_generator.py:208) | âš ï¸ **populate** it with detected markers; `generate` already aggregates `result.get("warnings")` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) |
| `review_data` payload (`script_content`, `script_language:"python"`, `confidence`, â€¦) | [sarah.py:714-725](src/ai_qa/agents/sarah.py:714) | âš ï¸ **add `warnings`** (low-risk payload enrichment; 13.5 renders it) |
| LLM retry (max 3, exponential backoff) on `_call_llm` / `_call_llm_with_vision` | [script_generator.py:231-235](src/ai_qa/pipelines/script_generator.py:231), [:299-303](src/ai_qa/pipelines/script_generator.py:299) | âœ… done â€” **keep** (NFR LLM retry â‰¤3) |
| LangChain string/list content normalization | [script_generator.py:270-291](src/ai_qa/pipelines/script_generator.py:270), [:350-364](src/ai_qa/pipelines/script_generator.py:350) | âœ… done â€” marker detection runs on the normalized string |

---

## Tasks / Subtasks

- [x] **Task 1 â€” Add `warnings` to the `GeneratedScript` review DTO (AC3)**
  - [x] In [sarah.py:26-37](src/ai_qa/agents/sarah.py:26) append `warnings: list[str] = Field(default_factory=list)` (import `Field` from pydantic; or `= []` via the existing `BaseModel`/`ConfigDict` pattern â€” keep it backward-compatible so the failed-generation placeholder at [sarah.py:341-349](src/ai_qa/agents/sarah.py:341) still constructs). This is the per-script surface for AC3 markers, mirroring 12.2's `TestCase.warnings`.

- [x] **Task 2 â€” Rewrite the generation prompts for AC3 (no unsafe inference) + AC2 (traceability comments) (AC2, AC3)**
  - [x] In [prompts/script_generation.py](src/ai_qa/prompts/script_generation.py) update `SCRIPT_GENERATION_SYSTEM_PROMPT` ([:7-18](src/ai_qa/prompts/script_generation.py:7)) and `SCRIPT_GENERATION_PROMPT` ([:20-73](src/ai_qa/prompts/script_generation.py:20)):
    - **Add the no-unsafe-inference rule (AC3):** when a test step does not give enough concrete detail to safely write the action/target/value/assertion (e.g. "submit the form" with no named control, an expected result with no observable outcome, a missing URL or input value), the model **MUST NOT invent** a guessed selector, URL, credential, or assertion. Instead it inserts an inline **`# TODO:`** (action needs detail) or **`# REVIEW:`** (decision/ambiguity) comment at that point, in the test case's own words, describing exactly what is missing. Keep the surrounding code runnable where possible.
    - **Reconcile the "output only valid Python code, no explanations" instruction** ([:18](src/ai_qa/prompts/script_generation.py:18), [:73](src/ai_qa/prompts/script_generation.py:73)): `# TODO:`/`# REVIEW:` are *inline Python comments* (valid code), so they are explicitly **allowed and required** where detail is missing. The ban is on prose/markdown *outside* the code, not on review comments â€” state this so the model does not suppress markers.
    - **Strengthen the AC2 traceability comments:** keep the existing "docstring describing what the test verifies" + "comments for each major step referencing the original test step number" ([:56-61](src/ai_qa/prompts/script_generation.py:56)). Make the step-number reference explicit (e.g. `# Step 2: <action>`).
    - **Keep** the function-signature, selector-priority, action-mapping, assertion-mapping, and best-practices sections unchanged (selector-stability *flagging* is 13.3).
  - [x] Apply the **same** no-unsafe-inference + marker rule to the vision variants `VISION_SCRIPT_GENERATION_SYSTEM_PROMPT` ([:163-174](src/ai_qa/prompts/script_generation.py:163)) and `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT` ([:134-161](src/ai_qa/prompts/script_generation.py:134)) â€” the vision path already has a "Low confidence (<0.5): Add comment, use alternative selector" instruction ([:157](src/ai_qa/prompts/script_generation.py:157)); align it with the `# TODO:`/`# REVIEW:` convention so both paths emit the same marker tokens.
  - [x] Do **not** alter `SCRIPT_GENERATION_WITH_HINTS_PROMPT` / `SELECTOR_GUIDANCE_PROMPT` / `ASSERTION_MAPPING_GUIDE` beyond consistency (they are reference/auxiliary; the live engine uses the four prompts above). Keep `__all__` ([:210-218](src/ai_qa/prompts/script_generation.py:210)) in sync if you add a new exported token/marker constant.

- [x] **Task 3 â€” Marker detection + warning surfacing in the engine (AC3)**
  - [x] In `ScriptGenerator._generate_single_script` ([script_generator.py:182-214](src/ai_qa/pipelines/script_generator.py:182)) after `script_content` is obtained and validated, **scan for review markers** and populate the returned `"warnings"`: add a small helper `_extract_review_warnings(script_content: str) -> list[str]` that finds lines matching `# TODO:` / `# REVIEW:` (case-insensitive, optional leading whitespace; recommend a compiled `re` pattern like `^\s*#\s*(TODO|REVIEW)\b[:\s]*(.*)$` per line) and returns the marker text (prefixed with the source so it reads as a warning, e.g. `"TODO: <text>"`). Return `{"success": True, ..., "warnings": <detected>}` instead of the hardcoded `[]` ([:213](src/ai_qa/pipelines/script_generator.py:213)). `generate` already extends `warnings` from `result.get("warnings")` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) â€” no change needed there.
  - [x] In `SarahAgent._generate_scripts` ([sarah.py:312-330](src/ai_qa/agents/sarah.py:312)) read the per-case warnings off `script_data` (the dict in `result.data[0]`) and pass them to the `GeneratedScript(... warnings=script_data.get("warnings", []))`. Mirror the same in `_regenerate_current_script` ([sarah.py:416-428](src/ai_qa/agents/sarah.py:416)) so a regenerated script keeps its markers.
  - [x] In `_present_current_script_for_review` ([sarah.py:714-725](src/ai_qa/agents/sarah.py:714)) add `"warnings": script.warnings` to `review_data` so AC3 markers reach the (future 13.5) review UI. Backend-only payload enrichment; no client change in 13.2.

- [x] **Task 4 â€” Durable source traceability in the script header (AC2)**
  - [x] Rewrite `_generate_script_header` ([script_generator.py:468-492](src/ai_qa/pipelines/script_generator.py:468)) so the docstring links to the **source test case durably**, not via the false `workspace/testcases/{name}.json` path ([:484](src/ai_qa/pipelines/script_generator.py:484)). Emit: the test-case **title**; the source-requirement reference when available â€” `source_requirement_name` and `source_url` via `getattr(test_case, "source_requirement_name", None)` / `getattr(test_case, "source_url", None)` (present after 12.2; omit the line when `None`/empty â€” Confluence stores `""`); the model and generation timestamp (keep). Keep the `import pytest` / `from playwright.sync_api import Page, expect` tail unchanged (AC1 conventions). Use `getattr` so the header degrades gracefully on the pre-12.2 `TestCase`.
  - [x] Confirm the header + per-step comments together satisfy AC2's "comments **or** metadata linking back to the source test case" â€” the docstring header is the metadata link; the per-step `# Step N:` comments (Task 2) are the in-body links.

- [x] **Task 5 â€” Backend tests (AC1, AC2, AC3)**
  - [x] **Prompt** ([tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py), new test class or extend): assert `SCRIPT_GENERATION_PROMPT` / `SCRIPT_GENERATION_SYSTEM_PROMPT` contain the no-unsafe-inference instruction and the `# TODO:`/`# REVIEW:` marker convention; assert they still forbid inventing selectors/URLs/credentials when unspecified. (Guards AC3 against regression.)
  - [x] **Marker detection** (AC3): feed `_generate_single_script` (or the new `_extract_review_warnings` helper directly) a mock LLM response containing `# TODO: exact submit control not specified` and assert the marker text is returned in the result `"warnings"`, flows through `generate` into `StageResult.warnings`, and lands on `GeneratedScript.warnings` via Sarah. A script with no markers yields empty warnings (back-compat â€” existing `test_generate_single_test_case` must still pass).
  - [x] **Header traceability** (AC2): **update** `test_header_contains_metadata` ([tests/pipelines/test_script_generator.py:334-346](tests/pipelines/test_script_generator.py:334)) â€” it currently asserts `"Source: workspace/testcases/" in header` ([:342](tests/pipelines/test_script_generator.py:342)), which 13.2 **removes**. Assert instead: header contains the title, the `import pytest` / `from playwright.sync_api import Page, expect` lines, and (with a `TestCase` carrying `source_requirement_name`/`source_url`) the durable source reference; assert it does **not** contain `workspace/testcases/`.
  - [x] **One-per-case + Python conventions** (AC1): existing `test_generate_single_test_case` / `test_generate_multiple_test_cases` already assert `len(result.data) == N`; keep. Confirm `_generate_filename` tests ([:217-270](tests/pipelines/test_script_generator.py:217)) still pass (Python `.py`). No new AC1 mechanism â€” verify-only.
  - [x] **Sarah** ([tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py)): a generated script with a TODO marker â†’ `GeneratedScript.warnings` populated and present in the `review_data` payload of `_present_current_script_for_review`. Reuse the existing scaffold (patches `ai_qa.agents.sarah.ScriptGenerator`; set the mocked `generate` return so `result.data[0]` carries a **NEW `"warnings"` key** â€” today the scaffold's mocked data dicts carry only `file_path`/`test_case_title`/`confidence`, so the dev must add `"warnings": ["TODO: â€¦"]`). Set `agent.phase = "script_review"` where 13.1's phase-dispatch requires it (see [13.1 Task 6 regression note](_bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md)). Do NOT resurrect workspace-path assertions.
  - [x] **Regression (warnings durability):** assert a regenerated script via `_regenerate_current_script` **retains** its warnings (markers survive regen, per Task 3), and the failed-generation placeholder ([sarah.py:341-349](src/ai_qa/agents/sarah.py:341)) still constructs with **empty** `warnings` after the field is added.
  - [x] If shared fixtures break, fix [tests/conftest.py](tests/conftest.py) **centrally** ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test.

- [x] **Task 6 â€” Verify (no migration)**
  - [x] Backend: `uv run pytest --no-cov` (whole suite â€” the coverage gate fails on subset runs; see [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). Mypy gate: `uv run mypy src`. Code must also pass **Pyrefly** â€” narrow optionals/`Any` before use: `StageResult.data`, `getattr(...)` results, and **`script_data.get("warnings", [])`** â€” the per-case dict is `dict[str, Any]`, so coerce to `list[str]` (e.g. a typed local) before assigning to `GeneratedScript.warnings`. No redundant casts/conversions; if you add a marker-token module constant, type it (avoid `Literal`-default pitfalls).
  - [x] Confirm **no Alembic migration** is required (`GeneratedScript` is in-memory Pydantic; the script is text artifact content; `TestCase` is a JSON model). State explicitly in Completion Notes.
  - [ ] Frontend: **no component change in 13.2.** Run `npm run typecheck` only to confirm nothing broke (the `review_data.warnings` payload is untyped on the client until 13.5). Note in Completion Notes that the typed script-review interface + warning rendering + syntax highlighting are deferred to **13.5** (full-stack sync handoff).

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/sarah.py` â€” Sarah agent (substantial Epic-5 implementation; 13.1 adds the selection gate in front).**

- `_generate_scripts` ([sarah.py:273-367](src/ai_qa/agents/sarah.py:273)) **already iterates one test case at a time** and calls `script_generator.generate(test_cases=[test_case], target_url=â€¦)` â€” so **AC1's one-script-per-test-case is structurally true today**. It prepends `_generate_script_header(test_case)` ([:315-316](src/ai_qa/agents/sarah.py:315)) and constructs a `GeneratedScript`. 13.2 adds `warnings` to that construction and changes nothing about the per-case loop.
- `process` ([sarah.py:146-206](src/ai_qa/agents/sarah.py:146)) today loads **all** test cases via `_load_test_cases()` ([:176-180](src/ai_qa/agents/sarah.py:176)). **13.1 rewrites this to generate from `self.confirmed_test_cases`.** 13.2 assumes that rewrite is in place; it does not touch the load path (the stale `"workspace/testcases/"` wording at [:175](src/ai_qa/agents/sarah.py:175)/[:187](src/ai_qa/agents/sarah.py:187)/[:209](src/ai_qa/agents/sarah.py:209) is 13.1's cleanup â€” if 13.1 already removed it, do not reintroduce; if not, that is a 13.1 gap, flag it).
- `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) has no `warnings` â€” Task 1 adds it.
- `_present_current_script_for_review` ([sarah.py:698-736](src/ai_qa/agents/sarah.py:698)) builds `review_data` with `confidence` but no `warnings` â€” Task 3 adds it. This method and the whole per-item **script** review loop (`handle_approve`/`handle_reject`/`handle_skip`/`handle_navigate`) are Epic-5 behavior; 13.2 only enriches the `review_data` payload, it does **not** change the review state machine (that's 13.5â€“13.7).
- `_regenerate_current_script` ([sarah.py:373-454](src/ai_qa/agents/sarah.py:373)) calls the generator **without** feedback ([:412-413](src/ai_qa/agents/sarah.py:412)) â€” feedback-into-prompt is **13.7**. 13.2 only mirrors the `warnings=` population here so regenerated scripts keep markers.

**`src/ai_qa/pipelines/script_generator.py` â€” the generation engine.**

- `generate` ([:64-131](src/ai_qa/pipelines/script_generator.py:64)) loops per test case â†’ `_generate_single_script` â†’ aggregates `data`/`errors`/`warnings`/confidence. It already extends `warnings` from each per-case `result.get("warnings")` ([:98-99](src/ai_qa/pipelines/script_generator.py:98)) â€” the channel exists; the per-case dict just always returns `[]` today ([:213](src/ai_qa/pipelines/script_generator.py:213)). Task 3 populates it.
- `_generate_single_script` ([:133-229](src/ai_qa/pipelines/script_generator.py:133)) does vision-assisted-or-LLM generation, length/empty validation, confidence calc. Marker detection slots in after the content is finalized ([after :206](src/ai_qa/pipelines/script_generator.py:206)).
- `_call_llm` / `_call_llm_with_vision` ([:236-377](src/ai_qa/pipelines/script_generator.py:236)) format the prompt with `test_case.model_dump_json(indent=2)` and call the LLM with retry. Tests patch `_get_llm_client` (object) or `ai_qa.pipelines.script_generator.LLMClient` (class) and set `mock_response.content`. Keep that seam.
- `_generate_script_header` ([:468-492](src/ai_qa/pipelines/script_generator.py:468)) â€” the AC2 rewrite target. The `Source: workspace/testcases/{source_filename}.json` line is the same stale-path lie 13.1 fixes in Sarah's messages; replace with durable source-test-case traceability.
- `_calculate_confidence` ([:494-552](src/ai_qa/pipelines/script_generator.py:494)) â€” **do not touch** (confidence is intentionally left alone, analog of 12.2 deferring to 12.3).

**`src/ai_qa/prompts/script_generation.py` â€” the prompts (the most load-bearing AC3 change).**

- `SCRIPT_GENERATION_SYSTEM_PROMPT` ([:7-18](src/ai_qa/prompts/script_generation.py:7)) ends with "Output only valid Python code without markdown formatting or explanations." `SCRIPT_GENERATION_PROMPT` ([:20-73](src/ai_qa/prompts/script_generation.py:20)) ends with "Output ONLY the Python test function code. Do not include markdown code blocks or explanations." Today the engine is told to **always produce runnable code**, which pushes the LLM to **invent** selectors/values/URLs when the test case is under-specified. AC3 inverts this: missing detail â†’ explicit `# TODO:`/`# REVIEW:` marker, never a guess. Reconcile the "no explanations" line so review comments are permitted (they are valid Python comments).
- The selector-priority block ([:32-39](src/ai_qa/prompts/script_generation.py:32)) and assertion map ([:48-54](src/ai_qa/prompts/script_generation.py:48), [:176-208](src/ai_qa/prompts/script_generation.py:176)) already encode FR8/FR9 guidance â€” **keep them**; 13.3 adds the *flagging* mechanics on top.

### The AC3 mechanic: markers + surfaced warnings, never invention (most load-bearing change)

AC3 is the direct analog of 12.2's AC2 ("ambiguous UI targets â†’ warnings, not invented selectors"), shifted one agent downstream:

1. **Prompt-side (LLM behavior):** the model writes an inline `# TODO:` / `# REVIEW:` comment, in the test case's own words, wherever it cannot safely infer a concrete action/target/value/assertion â€” and does **not** fabricate a URL, credential, selector, or assertion to fill the gap. This is the *behavioral* half.
2. **Engine-side (machine-readable surface):** the generator scans the produced script for those markers and lifts them into `GeneratedScript.warnings` + `StageResult.warnings`, so the user sees them in the review without reading every line. This is the *visibility* half, mirroring how 12.2 produced `TestCase.warnings`.

Keep the marker tokens simple and stable (`# TODO:` and `# REVIEW:`) â€” a future story (13.3) will *add* categories (brittle selector, ambiguous expected result) but should reuse the same channel rather than invent a parallel one. One ambiguity per marker line; include the step context in the text so 13.5 can tie it back to a step.

### Boundary fences (what 13.2 must NOT do)

- **13.3 (selectors/assertions):** do not add brittle-selector detection, selector-priority *enforcement* beyond the existing prompt guidance, or assertion-mapping warnings tied to specific source steps. 13.2's warnings cover *missing detail / unsafe inference* generically.
- **13.4 (SSO/secrets):** do not add browser-session reuse. Do honor the no-invent rule (no fabricated credentials/URLs) â€” that overlaps and is fine.
- **13.5 (review UX):** no frontend component, no syntax-highlight, no warning-rendering UI. Only enrich the backend `review_data` payload.
- **13.6/13.7 (edit/approve/regenerate):** do not wire feedback into the prompt; do not change the review state machine.
- **13.8 (artifact save):** do not expand save metadata or the save path.
- **Confidence:** do not change `_calculate_confidence`.

### Noticed defect (flag, do not fix unless Saved Q#4 says so)

`handle_approve` saves via `PipelineArtifactAdapter.save_script(Path(file_path).name or f"{tc.filename}.spec.ts", ...)` ([sarah.py:537-540](src/ai_qa/agents/sarah.py:537)) â€” the **`.spec.ts` fallback extension is wrong** (generated scripts are **Python** `.py`; `_generate_filename` produces `test_*.py`, header imports `pytest`). It only triggers when `file_path` is empty (failed-generation placeholder). This violates AC1's "project-standard Python conventions" in spirit but sits in the **save path** (Story 13.8's territory). Default: **flag it for 13.8**; fix it here only if Thuong opts in (Saved Q#4) â€” a one-char change (`.spec.ts` â†’ `.py`) plus the `kind="playwright_script"` artifact ([artifact_adapter.py:143-145](src/ai_qa/pipelines/artifact_adapter.py:143)).

### Architecture compliance (hard rules)

- **Agents never read/write storage directly â€” always via the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). Sarah's defined flow: derive user/project from thread â†’ read test cases via artifact service â†’ `script_generator.py` (+ `browser/agent.py`) â†’ save to `projects/{project_id}/test_scripts/` ([architecture.md:824-828](_bmad-output/planning-artifacts/architecture.md:824)). 13.2 stays inside the generator; it does not bypass the service.
- **Mandatory human review at every step â€” no auto-advance through a Review Request** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). The per-item script review is preserved; generation does not skip it.
- **Sarah model needs** ([architecture.md:1163-1167](_bmad-output/planning-artifacts/architecture.md:1163)): code-generation strength, browser-automation/tool-use compatibility, framework-aware output, optional vision â€” the prompt rewrite should reinforce framework-aware, runnable Python output while making gaps explicit (markers), not silently guessed.
- **No credential/secret leakage** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the no-invent rule explicitly forbids fabricating credentials/tokens/URLs; the `warnings`/`review_data` payload carries only marker text, titles, source refs, and confidence â€” never secrets or config dicts. The leak-canary convention applies.
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the enriched `review_data` is currently **untyped on the client** (no Sarah script-review consumer exists yet â€” 13.1 builds the *selection* panel, 13.5 builds the *script-review* panel). The typed script-review interface is created in 13.5. Flag this handoff in Completion Notes so 13.5 doesn't miss it.
- **Artifacts are project-scoped** under `projects/{project_id}/test_scripts/` ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280), [:346](_bmad-output/planning-artifacts/architecture.md:346)) â€” relevant to the save path (13.8), not generation.

### Library / framework constraints (from project-context.md)

- **Backend:** Python â‰¥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Must also pass **Pyrefly** â€” narrow `Optional` before use (`StageResult.data`, `getattr(...)` results, `script_data.get("warnings")`); no redundant casts/conversions; type any new module constant. `pytest.raises(Exception)` prohibited â€” specific exception type + `match=`. The generator path is **sync LLM call inside async** (no async-SQLAlchemy concerns).
- **Prompt strings are Python literals**, not markdown-linted; but this story file follows the markdown rules (lists `-`, MD036/MD052, table spacing).
- **Config:** script-gen settings exist on `AppSettings` ([config.py:121-136](src/ai_qa/config.py:121)): `script_generation_model` (default `"sonnet"`), `script_generation_temperature` (`0.0`), `script_generation_timeout` (`120`), `max_script_length` (`10000`), `confidence_threshold` (`0.7`). 13.2 needs no new setting (markers/detection are deterministic, no config knob).
- **No new packages. No Alembic migration.**

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/prompts/script_generation.py` (prompts), `src/ai_qa/pipelines/script_generator.py` (marker detection + header rewrite), `src/ai_qa/agents/sarah.py` (`GeneratedScript.warnings`, populate in `_generate_scripts`/`_regenerate_current_script`, `review_data.warnings`), `tests/pipelines/test_script_generator.py` (prompt + marker + header tests; **update** `test_header_contains_metadata`), `tests/test_agents/test_sarah.py` (warnings surfacing), possibly `tests/conftest.py`.
- **No new files required** (the `_extract_review_warnings` helper lives in `script_generator.py`). **No frontend files** (13.5 owns the script-review component + TS type).
- **No backend route/schema/REST changes** â€” the enriched `review_data` rides the existing WebSocket `send_message` metadata channel.

### Testing standards summary

- Backend: pytest. ScriptGenerator tests patch `_get_llm_client` (or `ai_qa.pipelines.script_generator.LLMClient`) and set `mock_response.content`; Sarah tests patch `ai_qa.agents.sarah.ScriptGenerator` (+ `PipelineArtifactAdapter`) and use `mock_project_context`/`mock_broadcast`. Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; live baseline prior epic = 1098 passed). Mypy gate is `src` only.
- Frontend: no Vitest/Playwright change in 13.2 (deferred to 13.5). Only `npm run typecheck` to confirm no breakage.

### Previous-story intelligence

- **Story 12.2 (Mary generation engine)** â€” the **direct analog**. Same shape: backend-only prompt rewrite + model field for `warnings` + "preserve ambiguity as warnings, never invent". 12.2 emitted plain-language targets + ambiguity warnings for Mary; 13.2 emits runnable Python + `# TODO:`/`# REVIEW:` markers for Sarah. **Key difference:** 12.2 added `warnings` to a persisted Pydantic `TestCase`; 13.2 adds `warnings` to the in-memory `GeneratedScript` (the script artifact persists as text; metadata is 13.8). Both leave confidence to a sibling story.
- **Story 13.1 (immediate prerequisite)** â€” restructures Sarah's lifecycle to confirm-before-generate and rewrites `process` to consume `self.confirmed_test_cases`. 13.2 extends that; it does not re-do the selection gate. Reuse 13.1's phase-dispatch (`agent.phase = "script_review"`) in tests.
- **Epic 5 (Sarah, `done`)** â€” built the `ScriptGenerator`/`VisionLocator` integration, the prompts, the per-item script review loop, chrome-path flow, and the existing confidence heuristic. 13.2 refines the prompt + adds the warning channel; it does not touch the review loop or vision plumbing.
- **Stories 13.3/13.4/13.5/13.7/13.8** â€” the explicit fences above. 13.3 specializes the warning channel to selectors/assertions; 13.4 adds SSO/secret rules; 13.5 builds the review UI that renders these warnings; 13.7 wires feedback regeneration; 13.8 saves the artifact + metadata.

### Git intelligence (recent work patterns)

Recent commits (`2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`) are Epic 10/11. **Epic 12 (12.1â€“12.5) and Story 13.1 are NOT implemented** â€” the live `sarah.py`/`script_generator.py`/`prompts/script_generation.py`/`TestCase` are pre-12.1/pre-13.1. Before relying on 13.1's `confirmed_test_cases` rewrite and 12.2/12.3's `TestCase` fields, **verify they are present in the live tree**; if unmerged, 13.2 is **blocked** â€” flag and stop rather than re-implementing upstream. Closest existing patterns to copy: [tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py) (engine test scaffold â€” header/confidence/filename/prompt), [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py) (Sarah lifecycle scaffold), and the **12.2 story** (the model-field-+-prompt-rewrite-+-warnings pattern).

### Sibling-story note (reusability)

13.2 establishes the **review-marker channel** (`# TODO:` / `# REVIEW:` in-script + `warnings` on `GeneratedScript`/`StageResult`/`review_data`). Keep it generic and single-purpose: **13.3** will reuse the same channel to flag brittle selectors and ambiguous assertions (do not let it invent a parallel warning surface), and **13.5** will render these warnings in the side-by-side review. Don't over-engineer a category taxonomy now (plain `list[str]`, one ambiguity per entry, step context in the text) â€” but avoid hardcoding that would block 13.3 from adding categorized warnings later.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-13.2] â€” ACs (lines 1281-1300); Epic 13 intro + FRs (1253-1257); sibling 13.3 selectors/assertions (1302-1322), 13.4 SSO (1324-1343), 13.5 review UX (1345-1365), 13.8 script save (1411-1430)
- [Source: _bmad-output/planning-artifacts/prd.md] â€” FR6 generate Python Playwright scripts (345), FR7 one file per test case, naming from title (346); FR8 stable selectors (347, primarily 13.3), FR9 assertion mapping (348, primarily 13.3)
- [Source: _bmad-output/planning-artifacts/architecture.md] â€” Sarah flow `script_generator.py â†’ â€¦ â†’ test_scripts/` (824-828), Sarah model needs (1163-1167), no-direct-storage (518, 533), no-auto-advance (271-272), project-scoped artifacts (280, 346), Test Script Generation summary FR5-9 (29)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] â€” mandatory review gate (188); Sarah/script step UX
- [Source: src/ai_qa/agents/sarah.py] â€” `GeneratedScript` (26-37, add `warnings`), `process` (146-206, 13.1 rewrites to confirmed set), `_generate_scripts` (273-367, per-case loop + header prepend 315-316 + GeneratedScript construct 321-327), `_regenerate_current_script` (373-454, feedback not wired 412-413), `handle_approve` `.spec.ts` fallback (537-540), `_present_current_script_for_review` review_data (698-736, esp. 714-725)
- [Source: src/ai_qa/pipelines/script_generator.py] â€” `generate` (64-131, warnings aggregation 98-99), `_generate_single_script` (133-229, warnings dict 213), `_call_llm`/`_call_llm_with_vision` (236-377), `_generate_filename` (436-466), `_generate_script_header` (468-492, stale workspace path 484), `_calculate_confidence` (494-552, do NOT touch)
- [Source: src/ai_qa/prompts/script_generation.py] â€” system + main prompt (7-73), with-hints/selector/assertion auxiliary prompts (76-208), vision variants (134-174), `__all__` (210-218)
- [Source: src/ai_qa/models.py:265-298] â€” `TestCase` (pre-12.2 fields + `filename`); `TestCaseStep` (244-262); 12.2/12.3 add `objective`/`source_requirement_*`/`source_url`/`feature_area`/`warnings`/`confidence*`
- [Source: src/ai_qa/pipelines/artifact_adapter.py] â€” `save_script` kind="playwright_script" (143-145), `load_test_cases` (139-141)
- [Source: src/ai_qa/config.py:121-136] â€” script-generation `AppSettings` fields (model/temperature/timeout/max_length/confidence_threshold)
- [Source: tests/pipelines/test_script_generator.py] â€” engine test scaffold; `test_header_contains_metadata` (334-346, asserts `Source: workspace/testcases/` 342 â†’ must change); confidence tests (273-328); filename tests (217-270); LLM mock seam (85-92, 360-369)
- [Source: tests/test_agents/test_sarah.py] â€” Sarah lifecycle test scaffold (patches ScriptGenerator + adapter)
- [Source: _bmad-output/implementation-artifacts/12-2-browser-automation-oriented-test-case-generation.md] â€” the analog generation-engine story (model field + prompt rewrite + warnings-not-invention pattern)
- [Source: _bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md] â€” the immediate prerequisite (confirm-before-generate, `confirmed_test_cases`, phase-dispatch, Frontend reality)
- [Source: project-context.md] â€” `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional, no redundant cast); no bare except; no `# type: ignore`; full-stack sync; security (no secrets in payloads/logs)

## Confirmed decisions (defaults locked by Thuong 2026-06-13 â€” "dÃ¹ng toÃ n bá»™ default")

All four formerly-open questions are resolved to their defaults. No pending input â€” implement exactly as stated.

1. **Warning mechanism shape = simple (CONFIRMED).** Use in-script `# TODO:` / `# REVIEW:` comment markers **plus** a `warnings: list[str]` on `GeneratedScript` populated by scanning the generated content for those markers â€” mirroring 12.2's `TestCase.warnings: list[str]`. No structured warning objects; one ambiguity per string with step context. (Structured warnings tied to step indices are 13.3's eventual need â€” deferred.)
2. **Marker tokens = `# TODO:` and `# REVIEW:` (CONFIRMED).** `# TODO:` for "action needs a concrete detail", `# REVIEW:` for "ambiguity/decision". Case-insensitive scan over both tokens.
3. **Header traceability content = title + source-requirement name/url via `getattr` (CONFIRMED).** Embed the test-case title, the source-requirement name + URL when present (12.2 fields, omit when empty/`None`), the model, and the timestamp; drop the `workspace/testcases/â€¦json` path entirely. (Source-test-case **artifact id** is not on the in-memory `TestCase`; 13.8 owns artifact-id linkage in save metadata.)
4. **The `.spec.ts` save-fallback defect = flag for 13.8, do NOT fix here (CONFIRMED).** Leave the one-line `.spec.ts` â†’ `.py` fix to 13.8 (the save path) to keep 13.2 scoped to generation. Flagged in Dev Notes "Noticed defect" for the 13.8 dev agent.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No blockers encountered. Prerequisites (Epic 12 + Story 13.1) confirmed present in working tree.

### Completion Notes List

- **AC1 (one-to-one, Python conventions):** Structural â€” no change needed; existing loop in `_generate_scripts` already handles one-per-case. `_generate_filename` produces `test_*.py` (confirmed by passing filename tests).
- **AC2 (traceability):** `_generate_script_header` rewritten to emit title + `source_requirement_name`/`source_url` via `getattr` (degrades gracefully on pre-12.2 `TestCase`). Removed the stale `workspace/testcases/{name}.json` line. Per-step `# Step N:` format now explicit in both main and vision prompts.
- **AC3 (no unsafe inference â†’ markers):** Added no-invent rule + `# TODO:`/`# REVIEW:` instructions to `SCRIPT_GENERATION_SYSTEM_PROMPT`, `SCRIPT_GENERATION_PROMPT`, `VISION_SCRIPT_GENERATION_SYSTEM_PROMPT`, and `VISION_ASSISTED_SCRIPT_GENERATION_PROMPT`. Added `_extract_review_warnings` compiled-regex helper in `script_generator.py`. Warnings populate from engine â†’ `GeneratedScript.warnings` â†’ `review_data["warnings"]`.
- **Pyrefly compliance:** `script_data.get("warnings", [])` coerced to `list[str]` via typed local before assignment in both `_generate_scripts` and `_regenerate_current_script`. `_MARKER_RE` is a class-level compiled `re.Pattern`; no type-annotation issues.
- **No Alembic migration:** `GeneratedScript` is in-memory Pydantic; scripts save as text artifact content. Confirmed explicitly.
- **No frontend change:** `review_data["warnings"]` payload is untyped on the client until Story 13.5 builds the script-review component and TS interface. Flagged in Completion Notes as a 13.5 handoff.
- **`.spec.ts` save-fallback defect:** Confirmed present at `sarah.py:706` (`f"{current_script.test_case.filename}.spec.ts"`). Deferred to Story 13.8 per confirmed default (Thuong 2026-06-13).
- **`__all__` unchanged:** No new exported constant added; `_MARKER_RE` is private. `_extract_review_warnings` is a public method but not re-exported from the module.

### File List

- `src/ai_qa/agents/sarah.py`
- `src/ai_qa/pipelines/script_generator.py`
- `src/ai_qa/prompts/script_generation.py`
- `tests/pipelines/test_script_generator.py`
- `tests/test_agents/test_sarah.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/13-2-python-playwright-script-generation.md`

## Change Log

- 2026-06-16: Story 13.2 implemented â€” GeneratedScript.warnings field, no-unsafe-inference prompt rewrites (all 4 prompt variants), _extract_review_warnings engine helper, durable script header traceability, full backend test suite (1277 passed, 0 failures). No migration, no frontend change. Status â†’ review.

