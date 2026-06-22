---
baseline_commit: 79f3f3cc797621c0ed3ae41e9b0c10edb59038fb
---

# Story 12.3: Confidence Scoring for Generated Test Cases

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Mary to score confidence for each generated test case and flag the low-confidence ones with their specific causes,
so that low-confidence outputs receive explicit review before they are handed to Sarah for script generation.

## Acceptance Criteria

Verbatim from [epics.md#Story-12.3](_bmad-output/planning-artifacts/epics.md) (lines 1187-1207), expanded with implementation defaults (see "Scope decisions" — confirm or correct).

### AC1 — Per-case confidence score/level + rationale stored with the item

- **Given** Mary generates a test case
- **When** quality analysis runs
- **Then** the test case receives a confidence **score** (0.0–1.0) **and** a confidence **level** (`high` / `medium` / `low`)
- **And** the confidence **rationale** (the factors that produced the score) is stored **on the generated test case itself** (so it persists when the case is saved)

### AC2 — Low-confidence flagging from poor source or unresolved warnings, with causes shown

- **Given** source content is incomplete, vague, contradictory, **or** the originating requirement carries unresolved Bob warnings
- **When** Mary scores the generated test case
- **Then** the test case is flagged `low` confidence
- **And** the specific causes (which structural gaps, which generation warnings, which source/Bob warnings) are shown to the reviewer

### AC3 — Low-confidence cases require an explicit decision before proceeding to Sarah

- **Given** one or more low-confidence test cases exist
- **When** the user attempts to proceed to Sarah (i.e. before Mary can complete and hand off)
- **Then** the workflow requires an explicit **approve** or **regenerate (reject + feedback)** decision for those low-confidence test cases
- **And** Mary does not reach `DONE` (the precondition for handing off to Sarah) while a low-confidence test case is still unreviewed

## Scope decisions (defaults — confirm or correct)

These are sensible defaults chosen from the code + ACs + planning docs; Thuong can override. Saved questions are listed at the end of this file.

- **This is a backend confidence-engine story** (the same shape as 12.2 — a backend generation story). The work is: add per-case confidence fields to the `TestCase` model, build a deterministic scoring + rationale engine, ingest the originating requirement's Bob warnings, surface confidence in Mary's existing review message, and enforce the AC3 gate at the agent/state level. **No new frontend component** is built here — the confidence **visualization** (green/yellow/red badge, causes panel) and the strongly-typed TS `TestCase` interface belong to **Story 12.4 (Mary Review Workflow)**. The confidence fields ride the existing `test_case` `metadata` channel automatically (`test_case.model_dump()` in `_present_current_test_case`).
- **Confidence is DETERMINISTIC / rule-based, NOT an LLM judge — CONFIRMED by Thuong 2026-06-12.** Consistent with Story 11.5's input-quality detection (deterministic), the existing `TestCaseExtractor._compute_single_confidence` (deterministic structural scoring), and the MVP "no extra LLM round-trip" posture. The score combines (a) structural completeness, (b) per-case generation `warnings` (12.2 — ambiguous UI targets), and (c) unresolved source/Bob `warnings` on the originating requirement artifact. A second LLM semantic/faithfulness pass is **out of scope**. "Contradictory" source content is detected only insofar as Bob flagged it (`QualityIssue`) or it surfaces as a structural gap — deterministic logic does **not** do semantic contradiction detection; that limitation is accepted for the MVP (an LLM judge can be added later if reviewers find the deterministic flag misses real contradictions).
- **AC3 is enforced at the backend / state-machine level here.** Mary's existing per-item review loop already requires an explicit approve/reject for **every** test case before it can transition to `DONE` (there is no bulk-approve / auto-advance path). 12.3 makes the low-confidence cases visibly flagged + adds a defensive guard so no low-confidence case can be skipped to `DONE`. The **frontend** "Proceed to Sarah" navigation affordance and the visual gate (e.g. a confirmation when low-confidence cases were approved) are **12.4**'s — today no Mary→Sarah navigation exists in `App.tsx` at all, so there is nothing to block at the UI yet. Flag this handoff in Completion Notes.
- **Save metadata expansion stays out of scope (12.5).** The per-case confidence fields persist **automatically** because `_write_approved_test_cases` serializes `model_dump_json()` and the new fields are part of the model — **no sidecar change is required**. Do **not** expand the `*.metadata.json` sidecar (that is 12.5). The one allowed touch: the sidecar currently hardcodes `"confidence": 1.0` ([mary.py:300](src/ai_qa/agents/mary.py:300)) — see Saved Question #3 for whether to correct it now or leave it to 12.5 (default: leave it, note it).
- **No Alembic migration.** `TestCase` is a Pydantic model serialized to JSON artifacts ([models.py:265](src/ai_qa/models.py:265)), not a DB table; the requirement `warnings` column already exists (11.7 migration `c8e6ace95b08`). Confirm explicitly in Completion Notes.

## Sequencing dependency (READ FIRST — critical)

**Stories 12.1 and 12.2 are `ready-for-dev`, NOT `done`.** As of this writing the working tree still holds the **pre-12.1** Mary (`process` reads `load_requirement_markdown()`, no `self.phase` / `self.confirmed_requirements`, `TestCase` has no `warnings`/`objective`/`source_*` fields). 12.3 builds directly on both and MUST be implemented **after 12.1 and 12.2 land**. Specifically, 12.3 assumes:

1. **From 12.1:** Mary's confirm-before-generate lifecycle (`self.phase`, `self.candidate_requirements`, `self.confirmed_requirements`, the `handle_approve` phase-dispatch, the `_check_preconditions` gate); the extended `PipelineArtifact` DTO (`source_type`/`source_url`/`thread_id`); `load_approved_requirements()`; `process` rewritten to generate from `self.confirmed_requirements`.
2. **From 12.2:** the extended `TestCase` model (`objective`, `test_data`, `source_requirement_id`/`name`, `source_url`, `feature_area`, **`warnings: list[str]`**); the `RequirementSource` dataclass + `extract(..., source=...)` / `extract_batch(..., sources=...)` source-stamping; **per-requirement generation** in `process` (cases generated one requirement at a time, in order); the enriched `_format_review_content`.

If 12.1/12.2 are not yet merged when you start, **stop and flag it** — do not re-implement them here. Reconcile against the live code and note any divergence in Completion Notes. 12.3 **extends** the 12.2 versions of `process` / `extract` / `RequirementSource` / `_format_review_content` / `_compute_single_confidence`; it does not re-create them.

## Tasks / Subtasks

- [x] **Task 1 — Add per-case confidence fields to the `TestCase` model (AC1)**
  - [x] In [models.py](src/ai_qa/models.py) `TestCase` (the 12.2 version) append, **all with backward-compatible defaults** (existing constructors in tests/fixtures must keep working):
    - `confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Per-case confidence score (0.0-1.0)")` — AC1.
    - `confidence_level: ConfidenceLevel | None = Field(default=None, description="Banded confidence: high/medium/low")` — AC1/AC2. Define `ConfidenceLevel = Literal["high", "medium", "low"]` as a module-level alias near `TestCase`. Default is `None` (Optional) so no Pyrefly `Literal`-default issue arises.
    - `confidence_rationale: list[str] = Field(default_factory=list, description="Human-readable factors behind the score (structural gaps, generation warnings, source warnings)")` — AC1/AC2 (the "causes shown to the reviewer").
  - [x] Update the `TestCase` docstring attribute list to document the new fields. Do **not** rename or repurpose 12.2's `warnings` (per-case generation warnings) — confidence **reads** `warnings`; the rationale may quote them, but they remain a distinct field.
  - [x] `TestCase` keeps `__test__ = False`. New fields serialize automatically via `model_dump`/`model_dump_json`, so they persist with **no migration** and flow to the client through `_present_current_test_case`'s `model_dump()`.

- [x] **Task 2 — Expose source warnings on the artifact DTO (AC2 input)**
  - [x] Extend the `PipelineArtifact` DTO ([artifact_adapter.py:18-26](src/ai_qa/pipelines/artifact_adapter.py:18), already extended by 12.1 with `source_type`/`source_url`/`thread_id`) with `warnings: list[dict[str, Any]] | None = None` (frozen dataclass — append with a default so existing constructors are unaffected).
  - [x] Populate it in `_to_pipeline_artifact` ([artifact_adapter.py:242-250](src/ai_qa/pipelines/artifact_adapter.py:242)) from `artifact.warnings` (the JSON column added by 11.7 — [db/models.py:154](src/ai_qa/db/models.py:154)). This is the canonical store of Bob's `QualityIssue`s for an approved requirement (written by `save_requirement(warnings=...)` — [artifact_adapter.py:90](src/ai_qa/pipelines/artifact_adapter.py:90)). The shape is `list[{category, location, message, impact}]` (`QualityIssue.to_dict()` — [pipelines/models.py:161-173](src/ai_qa/pipelines/models.py:161)).

- [x] **Task 3 — Build the deterministic confidence engine in `TestCaseExtractor` (AC1, AC2)**
  - [x] Define module-level threshold constants at the top of [test_case_extractor.py](src/ai_qa/pipelines/test_case_extractor.py) (tunable, documented): `CONFIDENCE_HIGH_THRESHOLD = 0.80`, `CONFIDENCE_MEDIUM_THRESHOLD = 0.55`, `WARNING_PENALTY_PER_CASE = 0.15`, `WARNING_PENALTY_PER_SOURCE = 0.10`.
  - [x] **Replace** `_compute_single_confidence` ([test_case_extractor.py:303-340](src/ai_qa/pipelines/test_case_extractor.py:303)) with an assessment that returns a structured result and recalibrates structural weights for the 12.2 model (objective/test_data now exist; selectors no longer stuffed into `automation_hints`). Recommended signature: `_assess_confidence(self, tc: TestCase, source_warnings: list[dict[str, Any]] | None) -> tuple[float, ConfidenceLevel, list[str]]` returning `(score, level, rationale)`. Implement the algorithm exactly as documented in **Dev Notes → "The deterministic confidence algorithm"** (structural additive score → warning penalties → banding where any per-case or source warning forces `low`). Keep the math pure and deterministic (no `Date.now`/random).
  - [x] **Stamp every generated case.** In `extract(...)` ([test_case_extractor.py:47](src/ai_qa/pipelines/test_case_extractor.py:47), the 12.2 version that already accepts `source: RequirementSource | None`), after parsing the cases and applying 12.2's source-id/name/url stamping, also call `_assess_confidence(tc, source_warnings)` for each case and set `tc.confidence`, `tc.confidence_level`, `tc.confidence_rationale`. Source warnings come from the `RequirementSource` (Task 4).
  - [x] **Aggregate from per-case scores.** Update `_compute_confidence` ([test_case_extractor.py:285-301](src/ai_qa/pipelines/test_case_extractor.py:285)) to average the now-stamped `tc.confidence` values (fall back to 0.0 for any `None`) instead of recomputing — single source of truth for the score. `StageResult.confidence` keeps its existing meaning (batch average).
  - [x] Do **not** change `_extract_json` / `_parse_llm_response` JSON contract. Confidence is computed in code from the parsed model, **not** requested from the LLM (do not add confidence fields to the prompt schema).

- [x] **Task 4 — Thread source warnings through `RequirementSource` (AC2)**
  - [x] Extend the `RequirementSource` carrier (defined by 12.2 in `test_case_extractor.py`) with `warnings: list[dict[str, Any]] | None = None` (frozen dataclass / `TypedDict` — append with default; back-compatible with 12.2 callers that pass none).
  - [x] In `extract(...)`, read `source.warnings` and pass it to `_assess_confidence`. In `extract_batch(...)` ([test_case_extractor.py:113](src/ai_qa/pipelines/test_case_extractor.py:113), 12.2 version with the `sources` param) the per-requirement `RequirementSource` already carries its warnings — no extra zip needed beyond 12.2's.

- [x] **Task 5 — Mary: feed source warnings, surface confidence, enforce the AC3 gate (AC2, AC3)**
  - [x] **Feed source warnings into generation.** In Mary's `process(...)` (the 12.2 per-requirement loop over `self.confirmed_requirements`), build each `RequirementSource` with `warnings=a.warnings` from the `PipelineArtifact` DTO (now exposed in Task 2), in addition to 12.2's `id`/`name`/`url`. This is the **only** link that turns "unresolved Bob warnings on the source" into a low-confidence flag on the generated case (AC2).
  - [x] **Surface confidence in the review.** Extend `_format_review_content` ([mary.py:217-263](src/ai_qa/agents/mary.py:217), as enriched by 12.2) to render, when present: a **Confidence** line (`level` + score, e.g. `Confidence: ⚠ LOW (0.42)`), and a **"Why this score"** bullet list of `confidence_rationale`. Keep 12.2's Objective/Source/Test-Data/Warnings sections. This is what makes AC2's "specific causes shown to the reviewer" true in the current plain-bubble review (the rich badge/panel is 12.4).
  - [x] `_present_current_test_case` ([mary.py:265-283](src/ai_qa/agents/mary.py:265)) already emits `test_case.model_dump()` — the new `confidence`/`confidence_level`/`confidence_rationale` flow to the client automatically. Optionally add a top-level `low_confidence: bool` and `low_confidence_count: int` to the message `metadata` so 12.4 (and a future proceed-gate UI) can react without re-deriving — recommended, low cost.
  - [x] **AC3 gate (state-machine level).** Track an **explicit reviewed/decided set** — do NOT key the guard off `current_review_index` (see the Dev Notes "AC3 mechanic" warning: at the DONE-transition point `current_review_index` already equals `len(self.test_cases)`, so an "at or after current index" predicate is always empty and the guard would be a no-op). Concretely: add `self._reviewed_indices: set[int] = set()` in `__init__`; `self._reviewed_indices.add(self.current_review_index)` in the per-item `handle_approve` branch (before the index advance) **and** on every successful `handle_reject` regeneration of the current case. Add a helper `_unresolved_low_confidence_indices() -> list[int]` returning every index `i` where `self.test_cases[i].confidence_level == "low"` **and** `i not in self._reviewed_indices`. Mary's per-item `handle_approve` (12.1's `phase == "test_case_review"` branch) already advances one case at a time and only transitions to `DONE` after the **last** case is approved — so every low-confidence case is necessarily reviewed on the normal path. **Add a defensive assertion in the DONE path**: before `transition_to(DONE)` in the test-case-review branch, if `_unresolved_low_confidence_indices()` is non-empty, re-present the first such case (`transition_to(REVIEW_REQUEST)`, set `current_review_index` to that index, call `_present_current_test_case`) instead of completing. Document that the per-item loop is the primary AC3 mechanism and this `_reviewed_indices`-keyed guard is belt-and-suspenders that **actually fires** against any future bulk-approve / auto-advance shortcut (a shortcut that jumps the index without recording each decision leaves those indices out of `_reviewed_indices`).
  - [x] **Generation summary signal (AC2/AC3 visibility).** After a successful generate, alongside 12.2's grouping summary, emit one `warning`-type message when low-confidence cases exist, e.g. `"⚠ {k} of {N} test cases are low confidence and need explicit review before proceeding to Sarah."` (omit the message when `k == 0`). This is the user-visible "you must decide" prompt in the current plain-chat flow.
  - [x] **Reconcile `handle_reject` regeneration** (the 12.2 version that reuses `self.confirmed_requirements` + the rejected case's `RequirementSource`): the regenerated case must be **re-scored** with the same source warnings so its confidence reflects the new content (it flows automatically because regeneration calls `extract` with the same `RequirementSource`, which now carries `warnings`). Verify the regenerated case's `confidence_level` is recomputed, not carried over.
    - **Note (a source-warning-driven `low` cannot be cleared by regeneration):** a case forced `low` **solely** by unresolved source/Bob `warnings` (structurally complete, no per-case `warnings`) will re-score `low` after **every** regeneration — the source warnings live on the immutable approved `Artifact.warnings` column and are fed identically into each regen via `RequirementSource(warnings=a.warnings)` (step 4 forces `low` from non-empty `source_warnings`). Regeneration is for clearing **structural gaps** and **per-case ambiguity warnings**; the intended resolution for a source-warning-driven `low` is an explicit **approve**. Do not present regen as the way to clear that specific flag (the rationale note from algorithm step 5 makes this self-explaining to the reviewer) — and do not mistake the unchanged `low` level for a regen bug.

- [x] **Task 6 — Backend tests (AC1, AC2, AC3)**
  - [x] **Model** (model round-trip test): a `TestCase` with `confidence`/`confidence_level`/`confidence_rationale` round-trips through `model_dump()`/`model_dump_json()`; defaults (`None`/`None`/`[]`) hold when omitted (back-compat for existing fixtures).
  - [x] **Engine** ([tests/pipelines/test_test_case_extractor.py](tests/pipelines/test_test_case_extractor.py) — **rewrite** `TestConfidenceScoring`, lines 174-220, to the new algorithm/return shape): a complete, warning-free case → `high` + score in the documented band + a positive/empty-gap rationale; a minimal case (only title + steps) → lower score + rationale listing the missing structural fields; a case with a per-case `warning` → `low` regardless of structural score, with the warning in the rationale; a case whose `source_warnings` contains a Bob `QualityIssue` → `low` with `Source requirement issue (<category>): <message>` in the rationale; banding boundaries at `CONFIDENCE_HIGH_THRESHOLD` / `CONFIDENCE_MEDIUM_THRESHOLD`.
  - [x] **Stamping**: `extract` with a `RequirementSource` (incl. `warnings`) stamps `confidence`/`confidence_level`/`confidence_rationale` on every returned case; `_compute_confidence` returns the average of the stamped per-case scores.
  - [x] **DTO** ([tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py)): `_to_pipeline_artifact` / `load_approved_requirements` exposes `warnings` from the `Artifact.warnings` column (set via `save_requirement(warnings=[...])`); `None` when the column is null.
  - [x] **Mary** ([tests/test_agents/test_mary.py](tests/test_agents/test_mary.py)): a confirmed requirement carrying Bob warnings → generated cases scored `low` with the source cause in the rationale (assert the `RequirementSource(warnings=...)` is built from the DTO); `_format_review_content` includes the Confidence line + rationale; the low-confidence summary `warning` message is emitted when `k > 0` and omitted when `k == 0`; the AC3 guard **actually fires** — (a) normal path: each index added to `self._reviewed_indices`, the last-case approve reaches `DONE`; (b) bulk-advance regression: set `current_review_index = len(self.test_cases)` **without** adding a `low`-confidence case's index to `self._reviewed_indices`, then assert the DONE path re-presents that case (transitions to `REVIEW_REQUEST`, not `DONE`). This guards against the vacuous-guard trap (a `current_review_index`-keyed predicate would pass this regression silently). Update fixtures: existing Mary tests patch `PipelineArtifactAdapter` and the extractor — set 12.1/12.2 state (`confirmed_requirements`, per-requirement extractor calls).
  - [x] Reconcile/rename any tests 12.1/12.2 already rewrote (e.g. `test_process_reads_requirements_from_workspace`). Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; live baseline prior epic = 1098 passed). If happy-path Mary tests break because shared fixtures don't satisfy the 12.1 gate / 12.2 generation path, fix [tests/conftest.py](tests/conftest.py) **centrally** (per [agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test.

- [x] **Task 7 — Verify (no migration; full-stack sync note)**
  - [x] Backend: `uv run pytest --no-cov` (full suite) green. Mypy gate: `uv run mypy src` clean. Code must also pass **Pyrefly** — narrow optionals (`source`, `source.warnings`, `ctx.project_id`, `StageResult.data`) before use; no redundant casts/conversions; for the `ConfidenceLevel` `Literal`, return values from `_assess_confidence` should be typed via a module constant or annotated local (avoid bare-string-into-`Literal` assignment — Pyrefly `bad-assignment`).
  - [x] Confirm **no Alembic migration** is needed (Pydantic JSON model + the `warnings` column already exists) — state explicitly in Completion Notes.
  - [x] Frontend: no component change in 12.3. Run `npm run typecheck` only to confirm nothing broke (it won't — the `test_case` payload is untyped on the client until 12.4). Note in Completion Notes that the TS `TestCase` interface + the confidence **visualization** (green/yellow/red badge, causes panel) + the "Proceed to Sarah" UI gate are deferred to **12.4** (full-stack sync handoff).

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/models.py` — `TestCase` ([:265-298](src/ai_qa/models.py:265)).** Pydantic model. Today (pre-12.2) it has `title`, `preconditions`, `steps`, `expected_results`, `automation_hints`, `tags`, plus a `filename` property. 12.2 adds `objective`, `test_data`, `source_requirement_id/name`, `source_url`, `feature_area`, `warnings`. **12.3 adds the confidence triple** (`confidence`, `confidence_level`, `confidence_rationale`). All serialize via `model_dump_json` on save → persist with **no migration**. Keep `__test__ = False`.

**`src/ai_qa/pipelines/test_case_extractor.py` — the engine.**
- `_compute_single_confidence` ([:303-340](src/ai_qa/pipelines/test_case_extractor.py:303)) is **deterministic** today: title 0.2, steps 0.3 (+0.1 well-formed bonus), expected_results 0.2, **automation_hints 0.2**, preconditions 0.1. 12.2 stops stuffing invented selectors into `automation_hints`, so the 0.2 hints reward is now mostly dead weight — **12.3 recalibrates** (reward `objective` + structural completeness instead; demote `automation_hints`). The existing exact-float tests ([test_test_case_extractor.py:174-220](tests/pipelines/test_test_case_extractor.py:174)) assert `1.0` / `0.6` / `0.0` and **will be rewritten** to the new algorithm + richer return shape.
- The per-case score is currently only averaged into `StageResult.confidence` ([:91](src/ai_qa/pipelines/test_case_extractor.py:91), [:285-301](src/ai_qa/pipelines/test_case_extractor.py:285)) and **thrown away per case** — nothing is stored on the `TestCase`. That is exactly AC1's gap.
- `extract` ([:47](src/ai_qa/pipelines/test_case_extractor.py:47)) (12.2 version) accepts `source: RequirementSource | None`; `_call_llm` mock seam is `ai_qa.pipelines.test_case_extractor.LLMClient` with `mock_client.invoke.return_value.content = <json>` — keep it. Confidence is **not** an LLM output; it is computed from the parsed model.

**`src/ai_qa/pipelines/artifact_adapter.py` — the DTO + loaders.** `PipelineArtifact` ([:18-26](src/ai_qa/pipelines/artifact_adapter.py:18)) is extended by 12.1 (`source_type`/`source_url`/`thread_id`) — 12.3 adds `warnings`. `_to_pipeline_artifact` ([:242-250](src/ai_qa/pipelines/artifact_adapter.py:242)) maps the `Artifact` row; add `warnings=artifact.warnings`. `save_requirement(warnings=...)` ([:90](src/ai_qa/pipelines/artifact_adapter.py:90)) is the producer that fills `Artifact.warnings` on approve — the round-trip is `Bob → save_requirement → Artifact.warnings → DTO.warnings → RequirementSource.warnings → _assess_confidence`.

**`src/ai_qa/db/models.py` — `Artifact`.** `warnings: Mapped[list[dict[str, Any]] | None]` is a plain `JSON` column ([:154](src/ai_qa/db/models.py:154)) — loaded by default (not a relationship, no eager-load needed). `source_type`/`source_url`/`thread_id` at [:152-153](src/ai_qa/db/models.py:152)/[:145](src/ai_qa/db/models.py:145).

**`src/ai_qa/pipelines/models.py` — `QualityIssue` ([:161-173](src/ai_qa/pipelines/models.py:161)).** `{category, location, message, impact}`. `QualityCategory` ([:151-158](src/ai_qa/pipelines/models.py:151)) = `unsupported_content | missing_expected_results | missing_preconditions | vague_language | ambiguous_ui_reference | insufficient_content`. These are the "unresolved Bob warnings" AC2 names — map every category to "this source is incomplete/vague" and force `low`. There is **no** explicit `contradictory` category; deterministic logic cannot detect semantic contradiction (Saved Question #1).

**`src/ai_qa/agents/mary.py` — the agent (heavily rewritten by 12.1 + 12.2 before you start).**
- After 12.1/12.2, `process` iterates `self.confirmed_requirements`, materializes each, and calls `extract` with a per-requirement `RequirementSource`. **12.3 adds `warnings=a.warnings` to that `RequirementSource`.**
- `_format_review_content` (12.2 version, enriched from [:217-263](src/ai_qa/agents/mary.py:217)) — 12.3 adds the Confidence line + rationale bullets.
- `_present_current_test_case` ([:265-283](src/ai_qa/agents/mary.py:265)) emits `test_case.model_dump()` — confidence fields flow automatically.
- `handle_approve` (12.1's `phase`-dispatched per-item branch, originally [:138-161](src/ai_qa/agents/mary.py:138)) advances one case at a time; only `transition_to(DONE)` after the last case → AC3's per-item enforcement is **already structural**. Add the defensive guard in this branch.
- `_write_approved_test_cases` ([:285-305](src/ai_qa/agents/mary.py:285)) saves via `model_dump_json` → confidence persists automatically. The sidecar's hardcoded `"confidence": 1.0` ([:300](src/ai_qa/agents/mary.py:300)) is **12.5's** to reconcile (Saved Question #3) — do not expand the sidecar here.

### The deterministic confidence algorithm (the single most load-bearing spec)

Implement `_assess_confidence(tc, source_warnings) -> (score, level, rationale)` exactly as below. All weights live in module constants so they are tunable + testable.

1. **Structural additive score** (weights sum to 1.0; append a rationale string for each *missing* field):
   - title present and ≠ `"Untitled Test Case"`: **+0.15** (else rationale: `"Missing or placeholder title"`)
   - `objective` non-empty (12.2 field): **+0.15** (else `"No objective stated"`)
   - `steps` non-empty: **+0.20**; **+0.10** bonus if **every** step has non-empty `action` AND `target` (else `"{n} step(s) missing an action or target"`)
   - `expected_results` non-empty: **+0.20** (else `"No expected results — outcome not verifiable"`)
   - `preconditions` non-empty: **+0.10** (else `"No preconditions specified"`)
   - `test_data` non-empty **OR** no step carries `data`: **+0.10** (else `"Steps use input data but no consolidated test_data listed"`)
2. **Warning penalties** (clamp final to `[0.0, 1.0]`):
   - per per-case `warning` (12.2 ambiguous-target strings): subtract `WARNING_PENALTY_PER_CASE` (0.15); append the warning verbatim to the rationale.
   - per source/Bob warning in `source_warnings`: subtract `WARNING_PENALTY_PER_SOURCE` (0.10); append `f"Source requirement issue ({category}): {message}"`.
3. **`score`** = `clamp(structural_score - penalties, 0.0, 1.0)`.
4. **`level` banding (AC2 — warnings force `low`):**
   - If `tc.warnings` is non-empty **OR** `source_warnings` is non-empty → `level = "low"` (regardless of score). This is the literal AC2: *"includes unresolved Bob warnings → flagged low confidence"*.
   - Else: `score >= CONFIDENCE_HIGH_THRESHOLD (0.80)` → `"high"`; `score >= CONFIDENCE_MEDIUM_THRESHOLD (0.55)` → `"medium"`; otherwise `"low"`.
5. **`rationale`** = ordered list. **If a warning forced the level to `low` while the structural `score` is still in the medium/high band (the step-4 override), the FIRST rationale entry MUST explain the override** so the displayed score does not read as contradictory to the `LOW` level — e.g. `f"Flagged LOW because unresolved warnings exist; the {score:.2f} score reflects structure only."`. Then append: structural-gap strings, then per-case warnings, then source warnings. If the case is `high` with no gaps, store a single positive note (`"All structural fields present; no source or generation warnings"`) so AC1's "rationale stored with the item" is always satisfied (never an empty rationale).

> **Limitation — AC2's "incomplete/vague" trigger is honored via Bob warnings, not raw structural gaps.** Structural gaps lower the `score` but do **not** by themselves force the `low` band. Incomplete/vague source content reliably forces `low` only when Bob recorded a `QualityIssue` on the originating requirement (any `QualityCategory` → source warning → step-4 force-low). Incompleteness Bob did **not** flag surfaces only as a reduced score + gap rationale and may land in `medium` (e.g. missing `objective` (−0.15) and `expected_results` (−0.20) → 0.65 → medium). This is the same accepted deterministic limit as the `contradictory` case; an LLM judge (the deferred option, ex-Saved-Question #1) is the future remedy. State this honestly rather than pretending deterministic scoring catches every "incomplete" source.

This is fully deterministic (no randomness, no clock) → stable unit tests. Thresholds/penalties are the knobs Thuong can tune later (Saved Question #2).

### AC3 mechanic — per-item review is the gate; the guard is belt-and-suspenders

AC3 says low-confidence cases need an explicit approve/regenerate decision "when the user attempts to proceed to Sarah". In this architecture **there is no shortcut to Sarah that bypasses per-item review**: Mary only reaches `DONE` after the user explicitly approves the *last* test case in the per-item loop ([mary.py:147-157](src/ai_qa/agents/mary.py:147)), and `DONE` is the precondition for any Bob/Mary→Sarah hand-off. So a low-confidence case **cannot** reach Sarah without an explicit decision — the requirement is satisfied structurally. 12.3's job is to (a) make low-confidence **visible** so the decision is informed (the Confidence line + the summary `warning`), and (b) add a defensive guard so a future bulk-approve / auto-advance path can't regress AC3. Do **not** invent a separate "proceed-to-Sarah" backend endpoint — the gate lives in the existing review loop. The **frontend** proceed affordance + visual gate is 12.4 (and Mary→Sarah navigation doesn't exist in `App.tsx` yet — there is nothing to wire here).

**Implementation warning — the guard MUST key off an explicit reviewed-index set, NOT `current_review_index`.** Approval in the per-item loop is positional/implicit: live `handle_approve` increments `self.current_review_index` *first* ([mary.py:144](src/ai_qa/agents/mary.py:144), comment "Mark current test case as approved (implicit by advancing index)") and only enters the DONE branch when `current_review_index >= len(self.test_cases)` ([mary.py:147](src/ai_qa/agents/mary.py:147)). So at the moment the guard runs ("before `transition_to(DONE)`"), `current_review_index == len(self.test_cases)` and a predicate scanning "indices at or after current_review_index" sees an **empty range** — it would never fire, shipping a no-op safety net. Record each decided index in `self._reviewed_indices` (in the per-item `handle_approve` branch and on successful regenerate) and have the guard flag any `low`-confidence index **not in that set**. That is the only formulation that actually catches a future bulk-approve/auto-advance regression (which jumps the index without recording each decision).

**Caveat — approve and regenerate are not interchangeable for every `low` cause.** AC3 offers "explicit approval **or** regeneration", but a case `low` purely because of immutable source/Bob warnings re-scores `low` after any regeneration (step 4 forces `low` from non-empty `source_warnings`, and those warnings are invariant across regens). Its **only** forward path is explicit approve. The workflow still terminates (DONE stays gated, approve always available) — this is a UX/expectation point, not an enforceability hole: surface it (step-5 rationale override note) so a regen "loop" on a source-warning case is not mistaken for a defect.

### Architecture compliance (hard rules)

- **`confidence: float | None` already exists on `StageResult`** ([architecture.md:469](_bmad-output/planning-artifacts/architecture.md:469), [:989](_bmad-output/planning-artifacts/architecture.md:989)) "used by downstream stages to decide whether to proceed or flag for review" — 12.3 keeps that batch-level field and **adds** per-case storage on `TestCase` (the AC1 gap).
- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), anti-pattern [:533](_bmad-output/planning-artifacts/architecture.md:533)). 12.3 reads source warnings through the adapter DTO; it adds no direct storage access.
- **Mandatory human review at every step — no auto-advance through a Review Request** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). The AC3 gate reinforces this; do not auto-approve low-confidence cases.
- **Low-confidence flagging is a first-class product goal** ([prd.md:117](_bmad-output/planning-artifacts/prd.md:117), [:183](_bmad-output/planning-artifacts/prd.md:183), [:253](_bmad-output/planning-artifacts/prd.md:253); FR22 [:384](_bmad-output/planning-artifacts/prd.md:384)) — "the tool highlights low-confidence generations… the problem is input quality, not the tool". The rationale (causes) directly serves this narrative: it tells the reviewer *why* the source produced a weak test case.
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): backend payload changes normally require a TS interface update. Here the `test_case` payload is **untyped on the client** until 12.4, so the TS `TestCase` interface + confidence visualization are created in 12.4. Flag this handoff in Completion Notes so 12.4 doesn't miss the new fields.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Must also pass **Pyrefly**: narrow `Optional` before use (`source`, `source.warnings`, `StageResult.data`); no redundant casts/conversions; for the `ConfidenceLevel` `Literal` use a typed module constant or annotated local for any default/return so a bare string isn't inferred as `str` (Pyrefly `bad-assignment`). `pytest.raises(Exception)` is prohibited — use a specific exception type + `match=`. The extractor path is **sync** (no async-SQLAlchemy concerns).
- **No new packages.** **No Alembic migration.** Confidence is internal deterministic logic — no external dependency, no web research required.
- **Markdown rules** apply to this story file (lists use `-`, MD036/MD052 etc.). The prompt itself is unchanged in 12.3 (do **not** add confidence fields to the LLM prompt schema).

### Project Structure Notes

- **Modified files (expected):** `src/ai_qa/models.py` (TestCase confidence triple + `ConfidenceLevel` alias), `src/ai_qa/pipelines/test_case_extractor.py` (`_assess_confidence` + stamping + `_compute_confidence` aggregate + `RequirementSource.warnings`), `src/ai_qa/pipelines/artifact_adapter.py` (DTO `warnings` + mapper), `src/ai_qa/agents/mary.py` (build `RequirementSource(warnings=...)`, Confidence in `_format_review_content`, low-confidence summary message, AC3 guard), `tests/pipelines/test_test_case_extractor.py` (rewrite `TestConfidenceScoring`), `tests/pipelines/test_pipeline_artifact_adapter.py` (DTO warnings), `tests/test_agents/test_mary.py`, possibly `tests/conftest.py`.
- **No new files required** (`ConfidenceLevel` lives in `models.py`; thresholds live in `test_case_extractor.py`). **No frontend files** (12.4 owns the component + TS type + visualization).
- **No backend route/schema/REST changes** — confidence rides the existing WebSocket `send_message` metadata channel and persists in the test-case JSON artifact.

### Testing standards summary

- Backend: pytest, in-memory SQLite for the adapter test (copy the scaffold in [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py) / [tests/unit/test_artifact_service_provenance.py](tests/unit/test_artifact_service_provenance.py)). Mock `LLMClient` at `ai_qa.pipelines.test_case_extractor.LLMClient`. Mary tests patch `PipelineArtifactAdapter` + the extractor and set 12.1/12.2 state. `pytest.raises(Exception)` prohibited — specific type. Run the **whole** suite with `--no-cov`. Mypy gate is `src` only.
- Frontend: no Vitest/Playwright change in 12.3 (deferred to 12.4). Only `npm run typecheck` to confirm no breakage.

### Previous Story Intelligence (12.1, 12.2, 11.5/11.7)

- **12.1** owns the confirm-before-generate lifecycle, the extended `PipelineArtifact` DTO (`source_type`/`source_url`/`thread_id`), `load_approved_requirements()`, and `process` consuming `self.confirmed_requirements`. 12.3 adds **`warnings`** to that DTO (12.1 did not).
- **12.2** owns the extended `TestCase` (incl. per-case `warnings`), `RequirementSource` + source-stamping, per-requirement generation, and the enriched `_format_review_content`. 12.2 explicitly **left confidence to 12.3**: *"Do not expand confidence scoring… leave `_compute_single_confidence` math alone… 12.2 only produces the per-case `warnings` that 12.3 will later consume."* 12.3 is the consumer. 12.2 also flagged that demoting `automation_hints` (no more invented selectors) means the old 0.2 hints reward should be recalibrated **here**.
- **11.5** introduced Bob's deterministic input-quality detection (`QualityIssue`, `QualityCategory`) and per-page `quality_issues`, and **explicitly deferred LLM semantic scoring to "Mary/12.3"** (project memory). The default for 12.3 is to stay deterministic and let the **source** Bob warnings (now persisted on the approved requirement's `Artifact.warnings`) drive the low-confidence flag — see Saved Question #1 if Thuong wants the LLM judge now.
- **11.7** made approved requirements carry provenance + `warnings` on the `Artifact` row; that column is the canonical source-warning store 12.3 reads. The pre-approval **draft** copy has `warnings = NULL` (and is excluded by 12.1's `source_type IS NOT NULL` filter), so only approved requirements (with real warnings) ever reach Mary.

### Git Intelligence

- Recent commits are Epic 10 (`b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`); Python was bumped 3.12→3.14 — never pin back. **Epic 11 is uncommitted in the working tree, and Stories 12.1 + 12.2 are NOT yet implemented** (the live `mary.py` / `test_case_extractor.py` / `TestCase` are the pre-12.1/12.2 versions). Before relying on 12.1's `confirmed_requirements` / extended DTO and 12.2's `TestCase.warnings` / `RequirementSource` / per-requirement `process`, **verify they are present in the live tree**; if 12.1/12.2 are not yet implemented, they are blocking prerequisites — flag and stop rather than re-implementing them.
- Closest existing test patterns: `tests/pipelines/test_test_case_extractor.py` (`TestConfidenceScoring`), `tests/test_agents/test_mary.py` (agent lifecycle), `tests/pipelines/test_pipeline_artifact_adapter.py` + `tests/unit/test_artifact_service_provenance.py` (DTO + provenance/warnings).

### Sibling-story note (reusability)

- **12.4 (Mary Review Workflow)** builds the rich per-item review card, the TS `TestCase` interface, and the confidence **visualization** (green/yellow/red badge + causes panel) + the "Proceed to Sarah" navigation/UI gate. Keep the `test_case` `model_dump()` payload **stable and complete** (confidence triple + 12.2 fields all included) and the optional `low_confidence`/`low_confidence_count` metadata so 12.4 only adds rendering, not re-derivation.
- **12.5 (Test Case Artifact Save)** expands the artifact-save metadata (source artifact IDs, **confidence data**, approval) — the per-case `confidence`/`confidence_level`/`confidence_rationale` on the model are the hooks it will lift into save metadata, and the `"confidence": 1.0` sidecar hardcode is 12.5's to reconcile (Saved Question #3).
- **Epic 13 (Sarah)** also flags low-confidence generations (FR22 spans Mary and Sarah). Keep the confidence triple machine-readable (numeric score + banded level + list-of-causes) so Sarah's script-generation confidence can mirror the same shape later.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-12.3] — ACs (lines 1187-1207); Epic 12 FRs FR5/FR22/FR27 (1141)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR22 flag low-confidence for mandatory review (384); low-confidence flagging narrative (117, 183, 228, 253)
- [Source: _bmad-output/planning-artifacts/architecture.md] — `StageResult.confidence` (469, 989), Mary flow (818-822), no-direct-storage (518, 533), no-auto-advance (271-272), Mary model needs (1157-1161), hallucination mitigation = confidence scoring + input quality + human review (73)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — confidence visualization green/yellow/red (81, 275), low-confidence amber token (682), Step 3 Create Test Cases (572-597), mandatory review gate (188)
- [Source: src/ai_qa/models.py:265-298] — `TestCase` (add confidence triple); `TestCaseStep` (244-262, unchanged)
- [Source: src/ai_qa/pipelines/test_case_extractor.py] — `extract` (47, 12.2 `source` param), `extract_batch` (113), `_parse_single_test_case` (253-283), `_compute_confidence` (285-301, re-aggregate), `_compute_single_confidence` (303-340, replace with `_assess_confidence`), LLM mock seam (166-186)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `PipelineArtifact` DTO (18-26, add `warnings`), `_to_pipeline_artifact` (242-250), `save_requirement(warnings=...)` (51-105), `load_approved_requirements` (added by 12.1)
- [Source: src/ai_qa/pipelines/models.py:151-173] — `QualityCategory` / `QualityIssue` (the source-warning shape Mary reads)
- [Source: src/ai_qa/db/models.py] — `Artifact.warnings` (154), `source_type`/`source_url` (152-153), `thread_id` (145)
- [Source: src/ai_qa/agents/mary.py] — `process` (61-136, 12.2 per-requirement version), per-item review (138-215), `_format_review_content` (217-263), `_present_current_test_case` (265-283), `_write_approved_test_cases` incl. hardcoded `confidence:1.0` (285-305, esp. 300)
- [Source: src/ai_qa/agents/base.py] — lifecycle (handle_start 307-339, handle_approve 341-347, handle_reject 349-387, transition_to 245-273)
- [Source: src/ai_qa/api/websocket.py] — dispatch (276-332), step→agent map incl. 3→Mary / 4→Sarah (356-362), navigate (335-388)
- [Source: tests/pipelines/test_test_case_extractor.py:174-220] — `TestConfidenceScoring` (rewrite to new algorithm)
- [Source: tests/test_agents/test_mary.py] — Mary agent test scaffold (reconcile with 12.1/12.2 renames)
- [Source: tests/pipelines/test_pipeline_artifact_adapter.py] + [tests/unit/test_artifact_service_provenance.py] — DTO + provenance/warnings test scaffold
- [Source: tests/conftest.py:27-63] — `mock_db`/`mock_project_context` (central fixture fix point)
- [Source: _bmad-output/implementation-artifacts/12-1-test-case-generation-input-selection.md] + [12-2-browser-automation-oriented-test-case-generation.md] — the lifecycle/DTO/model/engine this story builds on

## Saved Questions (for Thuong — confirm or correct)

1. **Deterministic vs LLM confidence (the big fork) — RESOLVED 2026-06-12: keep DETERMINISTIC.** Thuong chose the deterministic engine (structural + per-case warnings + source Bob warnings, no extra LLM round-trip). The LLM semantic/contradiction judge is explicitly deferred (not in 12.3). No action — this is the implemented design; recorded here for traceability.
2. **Thresholds & penalties.** Default bands: `high ≥ 0.80`, `medium ≥ 0.55`, else `low`; any per-case or source warning forces `low`; penalties 0.15/case-warning, 0.10/source-warning. OK, or different cutoffs?
3. **The hardcoded sidecar `"confidence": 1.0`** ([mary.py:300](src/ai_qa/agents/mary.py:300)). Default = **leave it for 12.5** (the per-case confidence already persists in the test-case JSON via `model_dump_json`). Or correct it to the real per-case confidence now as a one-liner?
4. **AC3 scope split.** Default = enforce AC3 at the **backend/state level** here (per-item review already mandatory + defensive guard + visible flag), and defer the **frontend** "Proceed to Sarah" affordance + visual gate to **12.4**. Confirm 12.3 stays backend-only (no React component), like 12.2.

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

None — implementation was clean on first run.

### Completion Notes List

- **No Alembic migration** — `TestCase` is a Pydantic model serialized to JSON artifacts; `Artifact.warnings` column already exists from 11.7 migration (`c8e6ace95b08`). Confirmed.
- **12.1 not implemented** — built directly on 12.2's standalone `load_requirement_markdown()` approach (12.1's `self.confirmed_requirements` lifecycle absent). Noted as divergence from story spec; 12.1 can overlay the full confirm-before-generate lifecycle when implemented.
- **AC3 guard implemented with `_reviewed_indices: set[int]`** — the story's explicit warning against the vacuous `current_review_index`-keyed guard was respected. Guard fires on any future bulk-advance/auto-advance path that skips recording indices.
- **Sidecar `"confidence": 1.0` hardcode** (mary.py `_write_approved_test_cases`) — left as-is per default (Saved Question #3); per-case confidence persists via `model_dump_json()` in the test-case JSON artifact. 12.5 will reconcile.
- **TS `TestCase` interface + confidence visualization deferred to 12.4** — `test_case.model_dump()` payload already carries the confidence triple; 12.4 adds the TypeScript interface and green/yellow/red badge/panel.
- **Full suite: 1230 passed** (up from 1098 baseline); 0 failures, 0 regressions.
- **Mypy: clean** (79 files, no issues).
- **Frontend typecheck: clean** (no component changes in 12.3).

### File List

- `src/ai_qa/models.py` — added `ConfidenceLevel` type alias; added `confidence`/`confidence_level`/`confidence_rationale` fields to `TestCase`
- `src/ai_qa/pipelines/artifact_adapter.py` — added `warnings: list[dict[str, Any]] | None` to `PipelineArtifact` DTO; populated from `artifact.warnings` in `_to_pipeline_artifact`
- `src/ai_qa/pipelines/test_case_extractor.py` — added threshold/penalty constants; extended `RequirementSource` with `warnings`; replaced `_compute_single_confidence` with `_assess_confidence`; stamped per-case confidence in `extract()`; updated `_compute_confidence` to average stamped scores
- `src/ai_qa/agents/mary.py` — added `_reviewed_indices: set[int]`; fed `warnings=artifact.warnings` into `RequirementSource`; added Confidence line + rationale to `_format_review_content`; added low-confidence summary `warning` message; added AC3 guard in `handle_approve`; added `_unresolved_low_confidence_indices` helper; added `low_confidence`/`low_confidence_count` to `_present_current_test_case` metadata
- `tests/pipelines/test_test_case_extractor.py` — rewrote `TestConfidenceScoring`; added confidence round-trip tests to `TestCaseModel`; added stamping tests to `TestRequirementSourceStamping`
- `tests/pipelines/test_pipeline_artifact_adapter.py` — added `test_to_pipeline_artifact_exposes_warnings_from_artifact`
- `tests/test_agents/test_mary.py` — added `TestMaryConfidenceScoring` class (8 tests)
- `_bmad-output/implementation-artifacts/12-3-confidence-scoring-for-generated-test-cases.md` — status `ready-for-dev` → `review`; baseline commit added; tasks checked; dev agent record filled
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `12-3`: `ready-for-dev` → `review`

## Change Log

| Date | Version | Author | Description |
|------|---------|--------|-------------|
| 2026-06-16 | 1.0 | claude-sonnet-4-6 | Implemented Story 12.3: deterministic confidence engine (`_assess_confidence`), `ConfidenceLevel` type, per-case confidence triple on `TestCase`, AC3 guard (`_reviewed_indices`), source-warning threading via `RequirementSource.warnings` + DTO, confidence display in Mary review content |
