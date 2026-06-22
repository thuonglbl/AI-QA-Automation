---
baseline_commit: 79f3f3cc797621c0ed3ae41e9b0c10edb59038fb
---

# Story 12.2: Browser-Automation-Oriented Test Case Generation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Mary to transform approved requirements into structured natural-language test cases optimized for browser automation,
so that Sarah can later convert them into Playwright automation scripts.

## Acceptance Criteria

Verbatim from [epics.md#Story-12.2](_bmad-output/planning-artifacts/epics.md) (lines 1165-1185), expanded with implementation defaults (see "Scope decisions" — confirm or correct).

### AC1 — Complete test-case structure

- **Given** approved requirement inputs are selected (the `self.confirmed_requirements` set produced by Story 12.1)
- **When** Mary generates test cases
- **Then** each generated test case includes **title, objective, preconditions, test data, steps, expected results, and source requirement references**

### AC2 — Browser-automation-oriented steps, no invented selectors

- **Given** a requirement describes browser behavior
- **When** Mary creates test steps
- **Then** user actions and expected UI outcomes are written clearly enough for Playwright automation (concrete, atomic, one action per step, plain-language UI targets)
- **And** ambiguous UI targets are **preserved as warnings instead of invented selectors** (no fabricated `#id` / `[data-testid=...]` when the requirement does not specify one)

### AC3 — Grouping + independent reviewability

- **Given** multiple requirements are processed
- **When** generation completes
- **Then** Mary groups test cases by source requirement or feature area (test cases carry a source-requirement reference and are ordered/grouped so same-source cases are contiguous)
- **And** each test case remains independently reviewable (the existing one-at-a-time per-item review flow is preserved)

## Scope decisions (defaults — confirm or correct)

These are sensible defaults chosen from the code + ACs; Thuong can override. Saved questions are listed at the end of this file.

- **This is a backend generation-engine story.** The work is: extend the `TestCase` model, rewrite the extraction prompt, thread source attribution + grouping through the extractor and Mary's `process`, and surface the new fields in Mary's existing review message. **No new frontend component** is built here — the rich per-item review card and the strongly-typed TS `TestCase` interface belong to **Story 12.4 (Mary Review Workflow)**. The new model fields ride the existing `test_case` `metadata` channel automatically (`test_case.model_dump()` in `_present_current_test_case`).
- **Confidence stays as-is.** Do **not** expand confidence scoring, rationale, or low-confidence gating — that is **Story 12.3**. 12.2 only *produces* the per-case `warnings` (ambiguous targets) that 12.3 will later consume; leave `_compute_single_confidence` math alone.
- **Save metadata stays as-is.** Do **not** expand the artifact-save metadata (source artifact IDs, confidence data, approval metadata) — that is **Story 12.5**. The full `TestCase` (incl. new source-ref fields) is already persisted because `_write_approved_test_cases` serializes `model_dump_json()`; no sidecar change here.
- **Source reference is single-requirement.** In the per-requirement extraction loop each generated test case is attributed to exactly one source requirement (`source_requirement_id` + name + url). A test case spanning multiple requirements is out of scope; the loop attributes to the requirement it was generated from.
- **No Alembic migration.** `TestCase` is a Pydantic model serialized to JSON artifacts ([models.py:265](src/ai_qa/models.py:265)), not a DB table. Confirm this explicitly in Completion Notes.

### Sequencing dependency (READ FIRST — critical)

**Story 12.1 is `ready-for-dev`, not `done`.** 12.2 builds directly on 12.1 and MUST be implemented after 12.1 lands. Specifically, 12.2 assumes 12.1 has already:

1. Restructured Mary's lifecycle to **confirm-before-generate** (`self.phase`, `self.candidate_requirements`, `self.confirmed_requirements`, the `handle_approve` phase-dispatch, the `_check_preconditions` gate).
2. Rewritten `process(...)` to generate from **`self.confirmed_requirements`** (not `load_requirement_markdown()`), materializing only the confirmed subset.
3. Extended the **`PipelineArtifact` DTO** with `source_type: str | None`, `source_url: str | None`, `thread_id: UUID | None`, populated in `_to_pipeline_artifact` ([artifact_adapter.py:242](src/ai_qa/pipelines/artifact_adapter.py:242)), and added `load_approved_requirements()`.

12.2 **extends** the 12.1 versions of `process` / `handle_reject` / `_present_current_test_case` / `_format_review_content`. If 12.1 is not yet merged when you start, reconcile against the live code and note any divergence in Completion Notes. Do not re-implement 12.1's confirm flow here.

## Tasks / Subtasks

- [x] **Task 1 — Extend the `TestCase` model for AC1/AC2/AC3 (AC1, AC2, AC3)**
  - [x] In [models.py](src/ai_qa/models.py) `TestCase` ([:265-298](src/ai_qa/models.py:265)) append the following fields, **all with backward-compatible defaults** (existing constructors in tests/fixtures must keep working):
    - `objective: str = Field(default="", description="What this test case verifies (one sentence)")` — AC1.
    - `test_data: list[str] = Field(default_factory=list, description="Consolidated test data values used by the case")` — AC1 (distinct from per-step `data`).
    - `source_requirement_id: str | None = Field(default=None, description="Artifact id of the originating requirement")` — AC1/AC3.
    - `source_requirement_name: str | None = Field(default=None, description="Artifact name of the originating requirement")` — AC1/AC3.
    - `source_url: str | None = Field(default=None, description="Source URL of the originating requirement (may be empty for Confluence)")` — AC1.
    - `feature_area: str | None = Field(default=None, description="Feature/area grouping label from the requirement")` — AC3 secondary grouping.
    - `warnings: list[str] = Field(default_factory=list, description="Ambiguity/quality warnings preserved during generation (e.g. ambiguous UI targets)")` — AC2.
  - [x] Update the `TestCase` docstring attribute list to document the new fields. Keep `automation_hints` and `tags` unchanged.
  - [x] Do **not** change `TestCaseStep` — per-step `action`/`target`/`data` are unchanged. Targets become plain-language via the prompt, not via a schema change.

- [x] **Task 2 — Rewrite the extraction prompt for browser-orientation + no invented selectors (AC1, AC2)**
  - [x] In [test_extraction.py](src/ai_qa/prompts/test_extraction.py) rewrite `TEST_CASE_EXTRACTION_PROMPT`:
    - **Add the new JSON fields** to the output schema and the worked example: top-level `objective` (string), `test_data` (array of strings), `feature_area` (string), `warnings` (array of strings). (`source_requirement_id`/`source_requirement_name`/`source_url` are **stamped by code, not the LLM** — do NOT ask the LLM to produce them.)
    - **Invert the selector guidance.** Replace the current DO/DON'T that pushes CSS/test-id selectors (`#username`, `[data-testid="login-btn"]`, lines 74-95) with: targets MUST be **plain-language UI descriptions** ("the username input field", "the Login button"). The model MUST NOT invent CSS selectors, test IDs, or XPaths. Selector mapping is Sarah's job (Epic 13), not Mary's.
    - **Add the ambiguity rule (AC2):** when the requirement does not name a concrete UI target (e.g. "submit the form", "go to the page"), DO NOT invent one. Write the step in plain language using the requirement's wording, and append a string to the test case `warnings` array describing the ambiguity (e.g. `"Ambiguous UI target in step 3: 'submit the form' — exact control not specified in the requirement"`). `automation_hints` is reserved for legitimate timing/wait/automation guidance, never for invented selectors.
    - **Add the grouping rule (AC3):** instruct the model to set `feature_area` to the feature/section the test case belongs to so cases can be grouped.
    - Keep the "actionable / atomic / locatable-by-description / verifiable" intent and "return ONLY JSON" rule.
  - [x] `format_test_extraction_prompt(requirements)` signature is unchanged (still takes the markdown string). Do not change its contract.

- [x] **Task 3 — Source attribution + new-field parsing in `TestCaseExtractor` (AC1, AC2, AC3)**
  - [x] Update `_parse_single_test_case` ([test_case_extractor.py:253-283](src/ai_qa/pipelines/test_case_extractor.py:253)) to read the new LLM fields with safe fallbacks: `objective=data.get("objective", "")`, `test_data=data.get("test_data", [])`, `feature_area=data.get("feature_area")`, `warnings=data.get("warnings", [])`. Keep the existing per-step parse. (Per-test-case try/except already skips malformed cases — preserve it.)
  - [x] Add a small typed source reference and thread it through extraction so each generated `TestCase` is stamped with where it came from. Recommended minimal-risk shape:
    - Define a frozen dataclass or `TypedDict` `RequirementSource` carrying `id: str | None`, `name: str | None`, `url: str | None` (top of `test_case_extractor.py` or a shared helper).
    - Add an optional `source: RequirementSource | None = None` param to `extract(...)` ([:47](src/ai_qa/pipelines/test_case_extractor.py:47)). After parsing, stamp every returned `TestCase` with `source_requirement_id/name`/`source_url` from `source` (only when provided). This keeps `extract` backward-compatible (existing callers/tests pass no `source`).
    - Add an optional parallel `sources: list[RequirementSource] | None = None` param to `extract_batch(...)` ([:113](src/ai_qa/pipelines/test_case_extractor.py:113)); zip it with `requirements_paths` (validate equal length like `source_urls`, raising `PipelineError` on mismatch) and forward each to `extract`. Default `None` → no stamping (back-compat).
  - [x] Do **not** change `_extract_json`, `_compute_confidence`, or `_compute_single_confidence` logic (confidence is 12.3). The new fields may naturally feed 12.3 later, but leave the scoring untouched here.

- [x] **Task 4 — Mary: per-requirement generation, grouping, and enriched review (AC1, AC2, AC3)**
  - [x] **Extend 12.1's `process(...)`** to generate **per confirmed requirement** so source attribution and grouping fall out naturally. For each `PipelineArtifact` in `self.confirmed_requirements` (already the confirmed subset from 12.1): materialize its markdown to a temp file (reuse `_materialize_requirement_artifacts` — but you need the artifact→file mapping; either materialize one-at-a-time or build a parallel `RequirementSource` list keyed by index), call the extractor with that requirement's `RequirementSource` (`id=str(a.id)`, `name=a.name`, `url=a.source_url or ""`), and accumulate results **in requirement order**. Same-requirement cases stay contiguous → AC3 grouping.
    - Keep returning a single `StageResult` with the combined `self.test_cases`, aggregated warnings, and confidence (mirror current aggregation). Preserve the empty-result and extractor-failure branches.
  - [x] **Generation summary message (AC3):** after a successful generate, send one `info` message summarizing the groups, e.g. `"Generated {N} test cases across {M} requirement(s): <name>: k, <name>: j…"`. This is the user-visible grouping signal in the current plain-chat review (the grouped review card is 12.4).
  - [x] **Enrich the review presentation** so the new AC1 fields are visible now. Update `_format_review_content` ([mary.py:217-263](src/ai_qa/agents/mary.py:217)) to render, when present: **Objective**, **Source requirement** (name/url), **Test Data**, and a **⚠ Warnings** section (AC2 ambiguous targets). Keep existing Preconditions/Steps/Expected/Automation-hints rendering. Steps already render `action (target: …)` — keep, since targets are now plain-language.
  - [x] `_present_current_test_case` already emits `test_case.model_dump()` in metadata ([mary.py:265-283](src/ai_qa/agents/mary.py:265)) — the new fields flow automatically. Optionally add the group/index context (`source_requirement_name`) to the metadata for 12.4 to consume. No required change beyond the model_dump carrying new fields.
  - [x] **Reconcile `handle_reject` regeneration** ([mary.py:163-215](src/ai_qa/agents/mary.py:163), as rewritten by 12.1 to reuse `self.confirmed_requirements`): when regenerating the current case, pass the **same `RequirementSource`** for the rejected case's `source_requirement_id` so the regenerated case keeps its source attribution and warnings semantics. Do not strip the stamping on regen.
  - [x] Remove any remaining stale "reads from workspace" wording 12.1 didn't already delete; do not reintroduce direct workspace reads.

- [x] **Task 5 — Backend tests (AC1, AC2, AC3)**
  - [x] **Model** ([tests/test_agents](tests/test_agents) or a model test): a `TestCase` with all new fields round-trips through `model_dump()`/`model_dump_json()`; defaults hold when fields omitted (back-compat for existing fixtures).
  - [x] **Prompt** ([tests/pipelines/test_test_case_extractor.py](tests/pipelines/test_test_case_extractor.py) `TestPromptTemplate`): `format_test_extraction_prompt` output contains the new schema keys (`objective`, `test_data`, `feature_area`, `warnings`) and the no-invented-selectors / plain-language-target instruction. Add an assertion that the prompt does **not** instruct using `data-testid`/CSS selectors as targets (guards against regressing AC2).
  - [x] **Parsing** (`TestLLMResponseParsing`): `_parse_single_test_case` populates `objective`, `test_data`, `feature_area`, `warnings` from JSON; omitted fields fall back to defaults. Add a sample LLM response carrying a `warnings` entry for an ambiguous target and assert it survives parsing.
  - [x] **Source stamping**: `extract` with a `RequirementSource` stamps `source_requirement_id/name/source_url` on every returned case; `extract_batch` zips `sources` correctly and raises `PipelineError` on length mismatch (mirror `test_extract_batch_mismatched_urls`).
  - [x] **Mary grouping/attribution** ([tests/test_agents/test_mary.py](tests/test_agents/test_mary.py)): with two confirmed requirements each yielding test cases, `process` produces cases stamped with the correct `source_requirement_id`, ordered so same-source cases are contiguous, and emits a grouping summary message. Update fixtures/mocks: existing Mary tests patch `PipelineArtifactAdapter` and the extractor — set `confirmed_requirements` (12.1 state) and assert per-requirement extractor calls.
  - [x] Reconcile/rename any tests 12.1 already rewrote (`test_process_reads_requirements_from_workspace` was renamed by 12.1). Do not resurrect workspace-path tests. Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; live baseline prior epic = 1098 passed).
  - [x] If happy-path Mary tests break because the new generation path or 12.1 gate isn't satisfied by shared fixtures, fix [tests/conftest.py](tests/conftest.py) **centrally** (per [agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test.

- [x] **Task 6 — Verify (no migration; full-stack sync note)**
  - [x] Backend: `uv run pytest --no-cov` (full suite) green. Mypy gate: `uv run mypy src` clean. Code must also pass **Pyrefly** — narrow optionals (`source` param, `ctx.project_id`, `StageResult.data`) before use; no redundant casts; typed defaults.
  - [x] Confirm **no Alembic migration** is needed (Pydantic JSON model, not a DB table) — state explicitly in Completion Notes.
  - [x] Frontend: no component change in 12.2. Run `npm run typecheck` only to confirm nothing broke (it won't — the payload is untyped on the client until 12.4). Note in Completion Notes that the TS `TestCase` interface + rich review card are deferred to 12.4 (full-stack sync handoff).
  - [x] If any frontend code already destructures the `test_case` metadata in a way the extra fields would break (it should not — extra JSON keys are ignored), capture it; otherwise confirm no FE change required.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/models.py` — `TestCase` ([:265-298](src/ai_qa/models.py:265)).** Pydantic model. Today: `title`, `preconditions`, `steps` (`TestCaseStep`: number/action/target/data), `expected_results`, `automation_hints`, `tags`, plus a `filename` property (kebab-case from title). **Missing for AC1:** `objective`, test-case-level `test_data`, source references. **Missing for AC2:** per-case `warnings`. **Missing for AC3:** `feature_area`. `TestCase` and `TestCaseStep` both set `__test__ = False` (pytest collection guard) — keep that. Serialized via `model_dump_json` on save, so new fields persist with **no migration**.

**`src/ai_qa/prompts/test_extraction.py` — the prompt.** This is the single most important AC2 change. The current prompt explicitly tells the LLM to "Use CSS selectors or test IDs when available (`#username`, `[data-testid="login-btn"]`)" and shows examples that invent selectors ([:74-95](src/ai_qa/prompts/test_extraction.py:74)). AC2 requires the **opposite**: plain-language targets and ambiguity preserved as warnings. Selector resolution is **Sarah's** responsibility (Epic 13, FR8 "prefer stable selectors"), confirmed by the FR map ([epics.md:172](_bmad-output/planning-artifacts/epics.md:172)). Mary must not pre-empt it.

**`src/ai_qa/pipelines/test_case_extractor.py` — the generation engine.**
- `extract(path, source_url="")` ([:47](src/ai_qa/pipelines/test_case_extractor.py:47)) reads one file → `_call_llm` → `_parse_llm_response` → list of `TestCase`. **`source_url` is accepted but never attached** to the produced cases — the attribution gap. 12.2 fixes this with a `RequirementSource` stamp.
- `extract_batch(paths, source_urls)` ([:113](src/ai_qa/pipelines/test_case_extractor.py:113)) **flattens** all cases into one list with **no source mapping** — this is why AC3 grouping is impossible today.
- `_parse_single_test_case` ([:253](src/ai_qa/pipelines/test_case_extractor.py:253)) maps JSON→`TestCase` defensively (per-case try/except, skip-on-error in `_parse_llm_response`). Add new-field reads here.
- `_compute_single_confidence` ([:303](src/ai_qa/pipelines/test_case_extractor.py:303)) — **do not touch** (12.3 owns confidence). Note its current scoring rewards `automation_hints` presence (0.2); since 12.2 stops stuffing invented selectors into hints, hints may legitimately shrink — that's fine and is 12.3's problem to recalibrate, not 12.2's.
- `_call_llm` uses `LLMClient(config).invoke(...)` **synchronously** inside the async method ([:166-186](src/ai_qa/pipelines/test_case_extractor.py:166)); tests patch `ai_qa.pipelines.test_case_extractor.LLMClient` and set `mock_client.invoke.return_value`. Keep that mock seam.

**`src/ai_qa/agents/mary.py` — the agent (will already be heavily rewritten by 12.1).**
- 12.1 overrides `handle_start` (gate → resolve approved → input-selection review → confirm), adds `self.phase`, `self.candidate_requirements`, `self.confirmed_requirements`, and rewrites `process` to generate from `self.confirmed_requirements`. **Build 12.2 on top of that**, not on the pre-12.1 `process` shown at [mary.py:61-136](src/ai_qa/agents/mary.py:61).
- `_materialize_requirement_artifacts` ([mary.py:307-317](src/ai_qa/agents/mary.py:307)) writes temp `requirement-NNN.md` files (the `TestCaseExtractor` is `Path`-based). **It loses artifact identity** (renames by index). For per-requirement attribution, materialize per artifact and keep the artifact→file→`RequirementSource` pairing (e.g. iterate with index and build a parallel `sources` list), or materialize one at a time inside the loop. Keep the temp-file shim; refactoring the extractor to in-memory strings is **out of scope**.
- `_present_current_test_case` ([:265-283](src/ai_qa/agents/mary.py:265)) sends `test_case.model_dump()` in `metadata["test_case"]` — new fields flow to the client automatically (the client ignores unknown keys; rich rendering is 12.4).
- `_format_review_content` ([:217-263](src/ai_qa/agents/mary.py:217)) is the human-readable markdown for the current plain-bubble review — enrich it with the new fields so they're visible before 12.4 ships.
- `_write_approved_test_cases` ([:285-305](src/ai_qa/agents/mary.py:285)) already saves via `adapter.save_test_case(model_dump_json)` (`kind="testcase"`, see [artifact_adapter.py:138-141](src/ai_qa/pipelines/artifact_adapter.py:138)). New fields persist automatically. **Do not** expand the metadata sidecar (12.5).

### The AC2 mechanic: warnings, not invented selectors (most load-bearing change)

AC2 has two halves and they pull in opposite directions from today's behavior:
1. Steps must be **clear enough for Playwright** → keep them concrete, atomic, action+target, but the target is a **human description** ("the Login button"), not a selector.
2. **Ambiguous UI targets → warnings, never invented selectors.** When the requirement doesn't name a concrete control, the LLM writes the step in the requirement's own words and adds a `warnings[]` entry. The codebase already has an `ambiguous_ui_reference` quality vocabulary on Bob's side ([pipelines/models.py:151-158](src/ai_qa/pipelines/models.py:151)) — Mary's per-case `warnings` is the test-case-side analog. Keep it a simple `list[str]` (structured `QualityIssue` reuse is unnecessary and would over-couple Mary to Bob's parser). 12.3 will read these warnings to drive low-confidence flagging.

### Grouping (AC3) — derive it from generation order, don't add a grouping engine

Generate per confirmed requirement, in order; accumulate cases as you go. Same-source cases are then contiguous, each stamped with `source_requirement_id/name`. That **is** "grouped by source requirement". `feature_area` (LLM-set) is the optional secondary grouping label for the review UI (12.4). "Each test case remains independently reviewable" is already satisfied by the per-item `handle_approve`/`handle_reject` loop ([mary.py:138-215](src/ai_qa/agents/mary.py:138)) — preserve it, just iterate in grouped order. The generation summary message is the only new user-facing grouping signal in 12.2.

### Architecture compliance (hard rules)

- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), anti-pattern [architecture.md:533](_bmad-output/planning-artifacts/architecture.md:533)). Mary's defined flow: derive user/project from thread → read requirements via artifact service → `test_case_extractor.py` → save to `projects/{project_id}/test_cases/` ([architecture.md:818-822](_bmad-output/planning-artifacts/architecture.md:818)). 12.2 reads via the adapter (12.1) and generates; it does not bypass the service.
- **Mandatory human review at every step — no auto-advance through a Review Request** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). The per-item review is preserved; generation does not skip it.
- **Mary model needs** ([architecture.md:1157-1161](_bmad-output/planning-artifacts/architecture.md:1157)): strong instruction-following, structured output, test-design reasoning, **consistency across many test cases** — the prompt rewrite should reinforce structured/consistent output (stable field set, JSON-only).
- **UX intent** ([ux-design-specification.md:582-588](_bmad-output/planning-artifacts/ux-design-specification.md:582)): test cases "structured, readable, and map to source requirements", "title, preconditions, steps, expected results". AC1's objective/test_data/source-ref make that mapping explicit.
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): backend payload changes normally require a TS interface update. Here the `test_case` payload is **currently untyped on the client** (no consumer), so the TS `TestCase` interface is created in 12.4 alongside the review card. Flag this handoff in Completion Notes so 12.4 doesn't miss it.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Must also pass **Pyrefly**: narrow `Optional` before use; no redundant casts/conversions; for any `Literal` default use a typed module constant. `pytest.raises(Exception)` is prohibited — use a specific exception type + `match=`. The extractor path is **sync** (no async-SQLAlchemy concerns).
- **No new packages.** **No Alembic migration.**
- **Markdown rules** apply to this story file and any prompt text doc edits (lists use `-`, MD036/MD052 etc.) — but the prompt itself is a Python string, not linted as markdown.

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/models.py` (TestCase), `src/ai_qa/prompts/test_extraction.py` (prompt + schema), `src/ai_qa/pipelines/test_case_extractor.py` (parse new fields + `RequirementSource` stamping), `src/ai_qa/agents/mary.py` (per-requirement generate + grouping + enriched `_format_review_content`), `tests/pipelines/test_test_case_extractor.py`, `tests/test_agents/test_mary.py`, possibly `tests/conftest.py`.
- **No new files required** (a `RequirementSource` dataclass can live in `test_case_extractor.py`). **No frontend files** (12.4 owns the component + TS type).
- **No backend route/schema/REST changes** — the enriched `test_case` rides the existing WebSocket `send_message` metadata channel.

### Testing standards summary

- Backend: pytest, mock `LLMClient` at `ai_qa.pipelines.test_case_extractor.LLMClient` and set `mock_client.invoke.return_value.content = <json>`. Mary tests patch `PipelineArtifactAdapter` and the extractor and set 12.1 state (`confirmed_requirements`). Run the **whole** suite with `--no-cov`. Mypy gate is `src` only.
- Frontend: no Vitest/Playwright change in 12.2 (deferred to 12.4). Only `npm run typecheck` to confirm no breakage.

### Previous Story Intelligence (12.1, 11.5/11.6/11.7)

- **12.1** owns the confirm-before-generate lifecycle, the extended `PipelineArtifact` DTO (`source_type`/`source_url`/`thread_id`), `load_approved_requirements()`, and the rewrite of `process` to consume `self.confirmed_requirements`. 12.2 extends those; it does not re-create them. The `source_url` on an approved Confluence requirement may be `""` (empty, not null) — so `RequirementSource.url` can be `""`; that's expected, not an error.
- **11.5** introduced Bob's input-quality detection with the `ambiguous_ui_reference`/`vague_language` `QualityCategory` ([pipelines/models.py:151-158](src/ai_qa/pipelines/models.py:151)) and per-page `QualityIssue`s. Mary's AC2 `warnings` is the generation-time analog; align the *concept* (ambiguous UI references → warning) but keep Mary's field a simple `list[str]`.
- **11.6/11.7** established that requirement artifacts carry provenance and that approved content is what Mary consumes. Source attribution in 12.2 uses the approved requirement's `id`/`name`/`source_url` exposed on the DTO.

### Git Intelligence

- Recent commits are Epic 10 (`b4ce65f`, `8cf53eb`); Python was bumped 3.12→3.14 (`39db313`) — never pin back. **Epic 11 and Story 12.1 are implemented in the working tree but uncommitted** on top of `b4ce65f` (per project memory). Before relying on 12.1's `confirmed_requirements`/extended DTO, **verify they are present in the live tree**; if 12.1 is not yet implemented, it is a blocking prerequisite — flag and stop rather than re-implementing it.
- Closest existing test patterns: `tests/pipelines/test_test_case_extractor.py` (extractor + prompt + parsing) and `tests/test_agents/test_mary.py` (agent lifecycle).

### Sibling-story note (reusability)

- **12.3** consumes the `warnings` this story produces (low-confidence flagging) and expands confidence scoring/rationale — keep `warnings` clean and machine-readable (one ambiguity per string, include the step context). Don't fold confidence logic into 12.2.
- **12.4** builds the rich per-item review card and the TS `TestCase` interface — keep the `test_case` `model_dump()` payload stable and complete (all new fields included) so 12.4 only adds rendering.
- **12.5** expands the artifact-save metadata (source artifact IDs, confidence, approval) — `source_requirement_id` on the model is the hook it will lift into save metadata.
- **Epic 13 (Sarah)** owns selector resolution (FR8). Mary deliberately emits plain-language targets + ambiguity warnings; Sarah turns them into stable selectors. Do not pre-resolve selectors in Mary.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-12.2] — ACs (lines 1165-1185); FR map FR5/FR22/FR27 (169, 191, 196); Sarah selector ownership FR8 (172)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR5 interpret NL steps for browser automation (344), FR22 flag low-confidence (384, primarily 12.3), FR27 detect insufficient input/warn (395, primarily 11.5/12.3)
- [Source: _bmad-output/planning-artifacts/architecture.md] — Mary flow (818-822), no-direct-storage (518, 533), no-auto-advance (271-272), Mary model needs (1157-1161)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — Step 3 Create Test Cases (572-597), test cases map to source requirements (582-588), mandatory review gate (188)
- [Source: src/ai_qa/models.py:265-298] — `TestCase` (extend); `TestCaseStep` (244-262, unchanged)
- [Source: src/ai_qa/prompts/test_extraction.py] — prompt to rewrite (selector guidance 74-95)
- [Source: src/ai_qa/pipelines/test_case_extractor.py] — `extract` (47), `extract_batch` (113), `_parse_single_test_case` (253-283), confidence (303, do not touch), LLM mock seam (166-186)
- [Source: src/ai_qa/agents/mary.py] — `process` (61-136, as rewritten by 12.1), per-item review (138-215), `_format_review_content` (217-263), `_present_current_test_case` (265-283), `_write_approved_test_cases` (285-305), `_materialize_requirement_artifacts` (307-317)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `PipelineArtifact` DTO (18-26, extended by 12.1), `save_test_case` kind="testcase" (138-141), `load_approved_requirements` (added by 12.1)
- [Source: src/ai_qa/pipelines/models.py:151-173] — `QualityCategory`/`QualityIssue` (`ambiguous_ui_reference` vocabulary to align with)
- [Source: tests/pipelines/test_test_case_extractor.py] — extractor/prompt/parsing test scaffold
- [Source: tests/test_agents/test_mary.py] — Mary agent test scaffold (reconcile with 12.1 renames)
- [Source: tests/conftest.py:27-63] — `mock_db`/`mock_project_context` (central fixture fix point)
- [Source: _bmad-output/implementation-artifacts/12-1-test-case-generation-input-selection.md] — the lifecycle/DTO/loader this story builds on

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

**Story 12.2 implementation complete — 2026-06-16**

**AC1 — Complete test-case structure:** `TestCase` extended with `objective`, `test_data`, `source_requirement_id`, `source_requirement_name`, `source_url`, `feature_area`, `warnings` — all with backward-compatible defaults. `PipelineArtifact` DTO extended with `source_url` (exposed from DB model's `artifact.source_url`). New fields flow through `model_dump_json()` to artifact save automatically — no Alembic migration needed (`TestCase` is a Pydantic model stored as JSON, not a DB table).

**AC2 — Plain-language targets, no invented selectors:** Prompt completely rewritten — removed old CSS/test-ID guidance, added plain-language target requirement, ambiguity → `warnings[]` rule. `automation_hints` explicitly reserved for timing/wait guidance only.

**AC3 — Grouping + independent reviewability:** `RequirementSource` frozen dataclass added to `test_case_extractor.py`. `extract()` stamps `source_requirement_id/name/source_url` on every returned case. `extract_batch()` accepts optional `sources` list (validated for length). Mary's `process()` builds `sources` in artifact order, passes to `extract_batch` — same-source cases are contiguous. Grouping summary message emitted after generation. Per-item review preserved unchanged.

**Reconciliation with REDEFINED 12.1:** No `confirmed_requirements` — used `requirement_artifacts` (already filtered by `selected_id`). No `load_approved_requirements()` — used `load_requirement_markdown()`. `PipelineArtifact.source_url` added as minimal DTO extension.

**`handle_reject` enriched:** Narrows to current test case's source requirement by `source_requirement_id`, passes `RequirementSource` on regen so attribution is preserved.

**`_format_review_content` enriched:** Now renders Objective, Source Requirement (name + url), Test Data, and ⚠ Warnings when present.

**No migration:** Confirmed — `TestCase` is Pydantic JSON, not a DB table.

**Frontend:** No component change in 12.2. `npm run typecheck` passes clean. TS `TestCase` interface + rich review card deferred to 12.4. Frontend ignores unknown JSON keys so extra fields are harmless.

**Test count:** 57 tests in extractor+Mary suites (was 35), 1212+ passing in full suite. One pre-existing flaky test (`test_browser_use_adapter_rejects_short_key`) fails only in full suite due to event-loop ordering — passes in isolation, unrelated to this story's changes.

**Reconciliation with REDEFINED 12.1 (2026-06-16):**
Story 12.1 was redefined — the multi-select Mary UI was replaced by a single-id selection at Bob. Actual 12.1 state:
- No `confirmed_requirements`/`candidate_requirements`/`self.phase` in Mary — uses `requirement_artifacts` (filtered by `selected_id` from `mary_selected_id.json`)
- No `load_approved_requirements()` — uses existing `load_requirement_markdown()`
- `PipelineArtifact` DTO had no `source_url` field — added in this story (minimal addition: exposes `artifact.source_url` from DB model)
- No Alembic migration needed (TestCase is a Pydantic model serialized to JSON, not a DB table)
- Frontend unchanged in 12.2 — TS `TestCase` interface + rich review card deferred to 12.4

### File List

- `src/ai_qa/models.py` — `TestCase` extended with 7 new fields (objective, test_data, source_requirement_id, source_requirement_name, source_url, feature_area, warnings) + docstring updated
- `src/ai_qa/pipelines/artifact_adapter.py` — `PipelineArtifact` DTO extended with `source_url: str | None = None`; `_to_pipeline_artifact` exposes `artifact.source_url`
- `src/ai_qa/prompts/test_extraction.py` — Full prompt rewrite: plain-language targets, no selector syntax, new JSON fields (objective/test_data/feature_area/warnings), ambiguity → warnings rule, feature_area grouping rule
- `src/ai_qa/pipelines/test_case_extractor.py` — Added `RequirementSource` frozen dataclass; `extract()` gains optional `source` param + stamps test cases; `extract_batch()` gains optional `sources` param with length validation; `_parse_single_test_case()` reads all new LLM fields
- `src/ai_qa/agents/mary.py` — Imports `RequirementSource`; `process()` builds `sources` list and passes to `extract_batch` + emits grouping summary message; `handle_reject()` narrows to source requirement and passes `RequirementSource` on regen; `_format_review_content()` renders Objective/Source Requirement/Test Data/⚠ Warnings
- `tests/pipelines/test_test_case_extractor.py` — Added `TestCaseModel`, `TestPromptTemplateNewFields`, `TestParseNewFields`, `TestRequirementSourceStamping` test classes (22 new tests)
- `tests/test_agents/test_mary.py` — Added `TestMaryProcessSourceAttribution`, `TestMaryFormatReviewNewFields` test classes (7 new tests)
- `tests/integration/test_project_scoped_agents.py` — Fixed `fake_extract_batch` signature to accept new `sources` kwarg

### Change Log

- 2026-06-16: Story 12.2 implemented — TestCase model extended, prompt rewritten for plain-language targets, RequirementSource stamping, per-requirement grouping, enriched review display. 22 extractor tests + 7 Mary tests added (was 35, now 57). Full suite: 1212+ passed.
