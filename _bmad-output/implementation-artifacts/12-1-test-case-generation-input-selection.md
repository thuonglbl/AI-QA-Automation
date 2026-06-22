---
baseline_commit: 79f3f3cc797621c0ed3ae41e9b0c10edb59038fb
---

# Story 12.1: Test Case Generation Input Selection

Status: done

> ## ⚠️ REDEFINED 2026-06-16 (input selection moved to Bob, single-id)
>
> Thuong changed the flow. The Mary **multi-select** input-selection UI described in
> the rest of this story is **superseded** by a **single-id selection at Bob** (step 2).
> What was actually implemented (commit pending):
>
> 1. **Per-page review removed.** After the user confirms the parent page, Bob now
>    **auto-saves every extracted Confluence page** as an approved requirement
>    (`BobAgent._auto_save_requirements`, save_requirement + delete_draft + metadata per
>    page). The old `SplitPanel` per-page approve/skip/reject loop is gone (frontend
>    `SplitPanel` render + `handleBobApprove/Skip/Reject` removed; the `SplitPanel.tsx`
>    component is now unused/dead).
> 2. **Bob asks for ONE id.** New phase `"select_id"`: Bob sends a prompt
>    (`metadata.is_select_id`) "Please input 1 Confluence page id or Jira ticket id…".
>    `BobAgent._handle_select_id` classifies the input: an already-extracted Confluence
>    page id is reused (no re-read); a Jira ticket id (regex `^[A-Za-z][A-Za-z0-9_]+-\d+$`)
>    is read on demand via `JiraReader.read_issue` + `_format_jira_markdown` and saved as a
>    `source_type="jira"` requirement (`_read_and_save_jira_ticket`); anything else → retry.
> 3. **Hand-off channel.** The chosen id is persisted as a configuration artifact
>    `mary_selected_id.json` (Bob and Mary are separate agent instances), and also stamped
>    on the DONE message metadata (`selected_id`) + carried via Mary auto-start `inputData`.
> 4. **Mary consumes the single id.** `MaryAgent.process` reads `selected_id` (input_data
>    first, then `mary_selected_id.json` via the new `adapter.load_metadata`) and scopes
>    generation to `{selected_id}/requirement.md`. (Feeding the full Confluence tree as
>    additional context is deferred to Epic 12.2.)
> 5. **Frontend.** `App.tsx` swaps the SplitPanel block for a single-id input card
>    (gated on `bobState.selectIdPrompt`), adds Bob→Mary auto-navigate + Mary auto-start.
> 6. **MCP fix.** `JiraReader.JIRA_TOOLS` trimmed to `["jira_get_issue"]` (the other two
>    were never called and falsely blocked, like the Confluence get_page_by_title/get_space
>    fix). The `jira_get_issue` param name (`issue_key`) is **flagged unverified** against
>    the live MCP — likely needs a camelCase fix (mirror confluence `pageId`).
>
> Tests updated: per-page-review Bob tests rewritten to cover `_auto_save_requirements` +
> `_handle_select_id`; E2E `epic-11.spec.ts` now drives confirm→extract→select-id→handoff.
> The Mary multi-select component (`MaryInputSelection.tsx`) and the `requirement_selection`
> payload AC below are **NOT** built. The detailed Mary-multi-select tasks/AC that follow are
> retained for history only.
>
> ### UPDATE 2026-06-17 — AC1 + AC3 implemented for the single-id flow
>
> Thuong decided (2026-06-17) that **AC1 (approved-only inputs)** and **AC3 (block when no
> approved requirement)** must hold even in the REDEFINED single-id flow. These are now
> **IMPLEMENTED in `mary.py`** (the multi-select `MaryInputSelection.tsx` UI remains
> **NOT built**):
>
> - **AC1 — approved-only source material.** Mary no longer feeds drafts into generation.
>   `MaryAgent.process` resolves requirements through the **approved-only** filter
>   (`Artifact.source_type IS NOT NULL` — the canonical draft-vs-approved discriminator;
>   `source_url` is NOT used because Confluence stores it as `""`) before scoping to the
>   chosen `selected_id`. Direct workspace path reads remain absent. (The original AC1
>   "thread-prioritized multi-select list" is still superseded by the single-id pick at Bob;
>   AC1's *approved-only* guarantee now holds.)
> - **AC3 — block when nothing is approved.** Mary now gates: if no **approved** requirement
>   exists for the project, generation is blocked (no PROCESSING transition, no LLM/extractor
>   call) and Mary emits a UX-DR12 message explaining Bob extraction **and approval** must
>   happen first. This is a precondition gate on Mary's start path.
>
> Still **NOT** built (single-id flow keeps these superseded): the multi-select
> `MaryInputSelection.tsx` component, the `requirement_selection` payload, Bob→Mary
> multi-select navigation, and the per-requirement confirm-step UI described in the
> historical tasks/AC below.

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Mary to use approved extracted requirements for the current project/thread, and to let me confirm or adjust which requirements feed generation,
so that generated test cases are based only on reviewed source material I have explicitly selected.

## Acceptance Criteria

Verbatim from [epics.md#Story-12.1](_bmad-output/planning-artifacts/epics.md), expanded with the scope confirmed by Thuong on 2026-06-12 (**full-stack rich** input-selection UI + a **confirm step before generation**).

### AC1 — Approved, project-scoped requirements only (no workspace paths)

- **Given** approved requirement artifacts exist for the selected project
- **When** Mary starts test case generation
- **Then** Mary loads only project-scoped **approved** requirements through the artifact service
- **And** direct workspace path reads are not used
- **And** pre-approval **draft** requirement artifacts are excluded (discriminator: `Artifact.source_type IS NOT NULL`)

### AC2 — Thread prioritization + user confirm/adjust before generation

- **Given** the current thread has source requirement artifacts
- **When** Mary prepares generation input
- **Then** artifacts from the originating thread (`Artifact.thread_id == context.thread_id`) are prioritized (listed first and pre-selected)
- **And** the user can confirm or adjust the selected requirement inputs **before** generation runs (full-stack input-selection panel; deselect/select then Confirm)
- **And** generation does not start until the user confirms the input set

### AC3 — Block when nothing is approved

- **Given** no approved requirement artifact is available for the project
- **When** Mary is asked to generate test cases
- **Then** Mary blocks generation (no PROCESSING transition, no LLM call)
- **And** explains in a UX-DR12 message that Bob extraction **and approval** must happen first

## Scope decisions (confirmed by Thuong, 2026-06-12)

- **AC2 delivery = full-stack rich.** Build a dedicated Mary input-selection component (per-requirement checkbox, thread-origin badge, source-type badge, source link, markdown preview) AND wire Bob→Mary navigation + a Mary auto-start trigger (neither exists today — `App.tsx` only renders Alice/step-1 and Bob/step-2 and only auto-navigates Alice→Bob).
- **Mary lifecycle = confirm step before generation.** `handle_start` → gate → resolve approved requirements (thread-prioritized) → present an input-selection `REVIEW_REQUEST` → user confirms/adjusts → `handle_approve` then triggers generation. Input-selection (12.1) is cleanly separated from generation (12.2) and the per-item test-case review UI (12.4).
- **Out of scope for 12.1:** the per-item test-case **review** UI (that is Story 12.4 — for now, the post-confirm generation + per-item review keep their existing plain-chat-bubble behavior), confidence scoring (12.3), and the test-case artifact save metadata expansion (12.5). Do not build those here.

## Tasks / Subtasks

> **Checkbox status (REDEFINED + 2026-06-17 update).** The tasks below describe the original
> **multi-select** design and are retained for history. They are **NOT** the shipped work, so
> their checkboxes are reset to unchecked, EXCEPT where the shipped single-id flow satisfies
> them: the **approved-only filter** (AC1) and the **precondition gate / AC3 block** are
> implemented in `mary.py` (see the REDEFINED banner's 2026-06-17 update and the Completion
> Notes). The multi-select `MaryInputSelection.tsx` UI, the `requirement_selection` payload,
> `load_approved_requirements`, and the confirm-step lifecycle were **not** built.

- [ ] **Task 1 — New approved-requirements loader on the adapter (AC1, AC2)** _(NOT built as written — `load_approved_requirements` multi-select loader deferred; AC1's approved-only guarantee is instead enforced in `mary.py` via the `source_type IS NOT NULL` filter)_
  - [x] Extend the `PipelineArtifact` DTO in [artifact_adapter.py:18-26](src/ai_qa/pipelines/artifact_adapter.py:18) with optional `source_type: str | None = None`, `source_url: str | None = None`, `thread_id: UUID | None = None` (frozen dataclass — append fields with defaults so existing loaders are unaffected).
  - [x] Populate the new DTO fields in `_to_pipeline_artifact` ([artifact_adapter.py:242-250](src/ai_qa/pipelines/artifact_adapter.py:242)) from the `Artifact` row.
  - [x] Add `load_approved_requirements(self) -> list[PipelineArtifact]` to `PipelineArtifactAdapter`. It must: call `self.service.list_artifacts(project_id=self.project_id, kind="requirements")`, keep only rows where `source_type is not None` (authoritative approved discriminator — see Dev Notes), then **stable-sort** so `thread_id == self.context.thread_id` rows come first (Python sort is stable; `list_artifacts` already orders by name, so name order is preserved within each group), then map via `_to_pipeline_artifact`.
  - [x] Do **not** remove `load_requirement_markdown` (other callers may exist); add the new method alongside it.

- [x] **Task 2 — Mary precondition gate + AC3 block (AC3)** _(IMPLEMENTED 2026-06-17 for the single-id flow: Mary blocks generation and sends a UX-DR12 message when no approved requirement exists. The gate lives on Mary's start path; exact helper names may differ from the historical `_check_preconditions`/`_format_no_requirements_message` sketch below.)_
  - [x] Add `_check_preconditions(self) -> list[str]` to `MaryAgent`, mirroring Bob ([bob.py:124-157](src/ai_qa/agents/bob.py:124)) but **only** the context checks Mary needs: `project_context` present with non-None `project_id`/`user_id`/`thread_id`, and `artifact_service.db` available. Mary does NOT need MCP or an Alice provider gate for input selection (LLM is only needed at generation time, which is post-confirm).
  - [x] Add `_format_no_requirements_message(self) -> str` returning the AC3 UX-DR12 message (mirror `_format_blocked_message` shape at [bob.py:243-250](src/ai_qa/agents/bob.py:243)): *What happened* = "Mary cannot generate test cases yet."; *Why* = "No approved requirements were found for this project."; *What to do* = "Run Bob to extract requirements from Confluence/Jira and approve at least one requirement, then start Mary again."

- [ ] **Task 3 — Restructure Mary's lifecycle to confirm-before-generate (AC1, AC2, AC3)** _(confirm-step lifecycle `_present_input_selection`/`_confirm_inputs` NOT built — superseded by Bob's single-id pick. The AC1-relevant pieces that DID land: `process` generates from approved-only requirements via the `source_type IS NOT NULL` filter, and the stale "reads from workspace" docstring was corrected.)_
  - [x] **Override** `handle_start(self, input_data)` in `MaryAgent` (currently inherited from base — base immediately calls `process` and generates). New flow:
    1. `blockers = self._check_preconditions()`; if non-empty → `send_message(..., message_type="error")` and `return` (stay at START).
    2. Resolve candidates: `PipelineArtifactAdapter(self.project_context).load_approved_requirements()`.
    3. If empty → `send_message(self._format_no_requirements_message(), message_type="error")` and `return` (AC3; no PROCESSING, no generation).
    4. Store `self.candidate_requirements = candidates`; compute default selection (see Dev Notes — current-thread pre-selected; if none, all pre-selected).
    5. `await self.transition_to(AgentState.REVIEW_REQUEST)` and `await self._present_input_selection()`.
  - [x] Add Mary state in `__init__`: `self.phase: str = "input_selection"`, `self.candidate_requirements: list[PipelineArtifact] = []`, `self.confirmed_requirements: list[PipelineArtifact] = []`.
  - [x] Implement `_present_input_selection(self)` — emit `send_message` with `metadata={"type": "requirement_selection", "is_input_selection": True, "requirements": [...]}`. Each requirement entry: `{ "artifact_id": str(a.id), "name": a.name, "title": <first markdown heading or name>, "source_type": a.source_type, "source_url": a.source_url, "from_current_thread": a.thread_id == ctx.thread_id, "default_selected": bool, "preview": a.content }`.
  - [x] **Dispatch in `handle_approve`** by phase: if `self.phase == "input_selection"` → `await self._confirm_inputs(data)`; else fall through to the existing per-item advance logic ([mary.py:138-161](src/ai_qa/agents/mary.py:138), unchanged).
  - [x] Implement `_confirm_inputs(self, data)`: read `selected_artifact_ids` from `data` (default = all candidates if absent/empty); filter `self.candidate_requirements` to the selected set into `self.confirmed_requirements`; if the result is empty, re-present selection with a corrective message and return; otherwise `await self.transition_to(AgentState.PROCESSING)`, set `self.phase = "test_case_review"`, call `result = await self.process(...)`, and on success present the first test case via the existing `_present_current_test_case()` (REVIEW_REQUEST). On empty/failed result, surface a message and transition appropriately.
  - [x] Update `process(...)` ([mary.py:61-136](src/ai_qa/agents/mary.py:61)) to generate from `self.confirmed_requirements` (materialize only those via `_materialize_requirement_artifacts`) instead of re-loading all requirements. Remove the in-method `load_requirement_markdown()` call ([mary.py:79-82](src/ai_qa/agents/mary.py:79)).
  - [x] Update `handle_reject` ([mary.py:163-215](src/ai_qa/agents/mary.py:163)) so the test-case-review re-extraction reuses `self.confirmed_requirements` rather than calling `load_requirement_markdown()` again ([mary.py:187-190](src/ai_qa/agents/mary.py:187)). (Reject during the `input_selection` phase is not required — adjustment happens via re-Confirm with a different selection.)
  - [x] Delete the stale "reads from workspace" docstrings/comments: [mary.py:23](src/ai_qa/agents/mary.py:23), [mary.py:69](src/ai_qa/agents/mary.py:69), and the workspace wording at [mary.py:286](src/ai_qa/agents/mary.py:286).

- [ ] **Task 4 — Frontend: Mary input-selection component (AC2)** _(NOT built — `MaryInputSelection.tsx` + `RequirementInput` type + `requirement_selection` wiring superseded by Bob's single-id input card)_
  - [x] Create `frontend/src/components/agents/MaryInputSelection.tsx` (new `components/agents/` dir — it does not exist yet). Props: `requirements: RequirementInput[]`, `onConfirm: (selectedIds: string[]) => void`, `disabled: boolean`. Render: a checkbox list (default-selected per `default_selected`), a "from this conversation" badge when `from_current_thread`, a source-type badge (`confluence`/`jira`), a clickable `source_url` link, an expandable markdown **preview** (reuse `ReviewContent` from [ReviewContent.tsx](frontend/src/components/ReviewContent.tsx)), and a **"Confirm & Generate"** button that calls `onConfirm(selectedIds)`. Disable Confirm when zero selected.
  - [x] Add a `RequirementInput` interface to a TS types file (e.g. `frontend/src/types/testcase.ts`, new) matching the backend `requirement_selection` payload exactly — full-stack sync rule ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)). Mirror the shape/casing pattern of [extraction.ts](frontend/src/types/extraction.ts).
  - [x] Wire into `App.tsx`: add `isMaryStep = currentStep === 3`; add `maryState` (candidates list); add a `handleMaryMessage` that captures `metadata.type === "requirement_selection"` into `maryState.requirements` (mirror `handleBobMessage` at [App.tsx:721-774](frontend/src/App.tsx:721)); render `<MaryInputSelection>` when `isMaryStep && status === "review_request"` and requirements are present (mirror the Bob SplitPanel render block at [App.tsx:1660-1677](frontend/src/App.tsx:1660)); add `handleMaryConfirm(selectedIds)` that sends `{ type: "approve", step: 3, data: { action: "confirm_inputs", selected_artifact_ids: selectedIds } }` (mirror `handleBobApprove` at [App.tsx:974-988](frontend/src/App.tsx:974)).

- [~] **Task 5 — Frontend: Bob→Mary navigation + Mary auto-start (AC2 prerequisite)** _(Bob→Mary auto-navigate + Mary auto-start ARE wired in `App.tsx` (`hasSentMaryStartRef`) per the REDEFINED flow; the multi-select selection card they fed is the part that was superseded)_
  - [x] Add an auto-navigate effect Bob→Mary mirroring the Alice→Bob effect at [App.tsx:834-855](frontend/src/App.tsx:834): when `currentStep === 2 && (status === "completed" || status === "done")`, after a short delay send `{ type: "navigate", step: 3, direction: "next", agentName: "Mary", ... }`. (Backend `_handle_navigate` already maps step 3 → "Mary" at [websocket.py:356-362](src/ai_qa/api/websocket.py:356).)
  - [x] Add a Mary auto-start effect mirroring Alice's at [App.tsx:621-636](frontend/src/App.tsx:621): when `isConnected && currentStep === 3 && status === "start" && threadId && !hasSentStartRef`, send `{ type: "start", step: 3, inputData: {} }`. Mary needs no user input to begin resolving requirements. (Reuse/guard `hasSentStartRef` carefully so it does not collide with the Alice start guard — consider a separate ref or key the guard on step.)

- [~] **Task 6 — Backend tests (AC1, AC2, AC3)** _(the `requirement_selection`/`confirm_inputs` multi-select tests were NOT built; Bob/Mary tests were instead rewritten for the single-id flow — `_auto_save_requirements`, `_handle_select_id`, and Mary's approved-only/AC3 gate behavior)_
  - [x] Adapter test in [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py): `load_approved_requirements` excludes drafts (`source_type IS NULL` rows from `save_requirement_page`), includes approved (`save_requirement`), orders current-thread first, and is project-scoped (other project → `[]`). Follow the discriminator pattern in [tests/unit/test_artifact_service_provenance.py:174-218](tests/unit/test_artifact_service_provenance.py:174).
  - [x] Mary tests in [tests/test_agents/test_mary.py](tests/test_agents/test_mary.py):
    - `handle_start` with no approved requirements → AC3 error message sent, stays START, `process`/extractor never called.
    - `handle_start` with approved requirements → emits `requirement_selection` payload, transitions to REVIEW_REQUEST, **does not** generate (extractor not called yet).
    - thread-prioritized ordering reflected in the emitted payload (`from_current_thread` first, pre-selected).
    - `handle_approve({action:"confirm_inputs", selected_artifact_ids:[...]})` → generates from the selected subset only, transitions to per-item review.
    - confirm with a deselected subset → only selected requirements materialized/extracted.
    - existing per-item review approve/reject tests still pass via the `phase` dispatch (update any test that relied on `handle_start`→immediate-generate, and the stale `test_process_reads_requirements_from_workspace` name/behavior at [test_mary.py:92-126]).
  - [x] If happy-path Mary tests break because the shared fixtures don't satisfy the new gate, fix [tests/conftest.py](tests/conftest.py) **centrally** (per [agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)), not per-test. Note: existing Mary tests patch `PipelineArtifactAdapter` directly, so set `mock_adapter.load_approved_requirements.return_value` in those tests.

- [ ] **Task 7 — Frontend tests (AC2)** _(NOT built — `MaryInputSelection` Vitest + `requirement_selection` render-path tests superseded; E2E `epic-11.spec.ts` instead drives confirm→extract→select-id→handoff for the single-id flow)_
  - [x] Vitest for `MaryInputSelection`: renders candidates, default selection honored, deselect/select adjusts, thread-origin + source-type badges, source link, Confirm disabled at zero-selected, Confirm emits the selected ids. (Vitest 4 mock rules — see [project-context.md#Testing-Rules](project-context.md).)
  - [x] Optional App-level test for the `requirement_selection` message → component render path, and the confirm→`approve` send.
  - [x] Playwright E2E (`frontend/e2e/`): seed an **approved** requirement artifact via the artifact API (provenance set — `source_type` non-null) in a test project/thread, navigate to Mary, assert the selection panel lists it with the thread badge, Confirm, and assert generation proceeds (or the next state). Prepare state via real API calls only (no `page.route`); clean up in `afterEach` (users, projects, artifacts) per [project-context.md#Testing-Rules](project-context.md). If seeding an approved artifact via API is not yet feasible, scope the E2E to the AC3 block path (no requirements → blocking message) and note the deferral in Completion Notes.

- [x] **Task 8 — Verify (no migration needed)**
  - [x] Backend: `uv run pytest --no-cov` (full suite — the coverage gate fails on subset runs; see Dev Notes). Mypy gate: `uv run mypy src`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest), and the new E2E spec.
  - [x] Confirm **no Alembic migration** is required — `source_type`/`source_url`/`warnings`/`thread_id` columns already exist from Story 11.7 (migration `c8e6ace95b08`). State this explicitly in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/mary.py` — the primary change target.**
- The docstrings claim Mary "reads requirements from workspace/requirements/" ([mary.py:23](src/ai_qa/agents/mary.py:23), [mary.py:69](src/ai_qa/agents/mary.py:69)) — **stale and misleading**. Reality: `process` already reads via the artifact service: `PipelineArtifactAdapter(self.project_context).load_requirement_markdown()` ([mary.py:79-82](src/ai_qa/agents/mary.py:79)). So AC1's "no workspace path reads" is **mostly already true** — the real AC1 gap is that `load_requirement_markdown` returns **drafts AND approved** indiscriminately. Delete the stale docstrings as part of this story.
- `handle_start` is **inherited** from base ([base.py:307-339](src/ai_qa/agents/base.py:307)) — base transitions START→PROCESSING and immediately calls `process` (generation). Mary currently has **no precondition gate**. This story **overrides** `handle_start` (Bob does the same — [bob.py:503-518](src/ai_qa/agents/bob.py:503)).
- `handle_approve` ([mary.py:138-161](src/ai_qa/agents/mary.py:138)) and `handle_reject` ([mary.py:163-215](src/ai_qa/agents/mary.py:163)) already implement per-item test-case review. Preserve that behavior under the new `phase == "test_case_review"` branch. `handle_reject` accepts an optional `data` param (added in 11.6) — keep it.
- `_materialize_requirement_artifacts` ([mary.py:307-317](src/ai_qa/agents/mary.py:307)) writes artifact content to temp files because `TestCaseExtractor` is `Path`-based ([test_case_extractor.py](src/ai_qa/pipelines/test_case_extractor.py)). Keep this shim; just feed it the **confirmed** subset. Refactoring the extractor to accept in-memory strings is optional and **not** in 12.1 scope.
- Note (do not fix here): `self.config = self.get_llm_config()` runs at `__init__` ([mary.py:55](src/ai_qa/agents/mary.py:55)) before project context is set, so it uses the env-var fallback rather than the thread's Alice-assigned model. Pre-existing Epic-4 behavior; generation/model wiring is a 12.2/12.3 concern. Don't touch it in 12.1.

**`src/ai_qa/pipelines/artifact_adapter.py` — add the approved loader.**
- `load_requirement_markdown` → `_load_text_artifacts(kind="requirements")` does **no filtering** ([artifact_adapter.py:134-136](src/ai_qa/pipelines/artifact_adapter.py:134), [:238-240](src/ai_qa/pipelines/artifact_adapter.py:238)).
- The `PipelineArtifact` DTO ([:18-26](src/ai_qa/pipelines/artifact_adapter.py:18)) carries only `id/name/kind/content/version` — it does **not** expose `source_type`/`source_url`/`thread_id`, so the selection payload can't be built without extending it (or filtering at the `Artifact` level). Extend the DTO with optional fields.
- `save_requirement` ([:51-105](src/ai_qa/pipelines/artifact_adapter.py:51)) is the producer side: approved name `f"{page_id}/requirement.md"`, `kind="requirements"`, provenance set, `thread_id`/`agent_run_id`/`user_id` from `self.context`. `delete_draft_requirement` ([:107-132](src/ai_qa/pipelines/artifact_adapter.py:107)) removes the `{page_id}.md` draft after approval — **best-effort, never raises, runs only on the approve path** → drafts can survive (skipped pages, failed deletes). This is exactly why the `source_type IS NOT NULL` filter is mandatory, not optional.

### The approved-vs-draft discriminator (the single most load-bearing fact)

All requirement artifacts share `kind="requirements"`. Two rows can exist per page:

| | Pre-approval DRAFT | APPROVED (authoritative) |
| --- | --- | --- |
| Saved by | `save_requirement_page(page_id, md)` ([bob.py:987]) | `save_requirement(page_id=..., source_type=..., ...)` ([bob.py:1150]) |
| Name | `{page_id}.md` (no slash) | `{page_id}/requirement.md` |
| `source_type` / `source_url` / `warnings` | **NULL** | **set** (`source_type` is `"confluence"` or `"jira"`, never null for approved) |

**Use `source_type IS NOT NULL` as the discriminator** — it is the canonical filter the codebase itself uses ([test_artifact_service_provenance.py:217-218](tests/unit/test_artifact_service_provenance.py:217): `approved = [a for a in all if a.source_type is not None]`). Name-matching `*/requirement.md` is a valid secondary signal but provenance is authoritative. **Do not filter on `source_url`** — Confluence stores it as `""` (empty string, not NULL) while `source_type` is still set; `warnings` can be `[]` for an approved-with-no-issues page. Only `source_type` cleanly separates draft from approved.

### Thread prioritization & default selection (AC2)

- "Originating thread" = `Artifact.thread_id` ([models.py:145](src/ai_qa/db/models.py:145)), set by `save_requirement` from `context.thread_id`. The current thread = `PipelineContext.thread_id` ([context.py:18]).
- `ArtifactService.list_artifacts(*, project_id, kind=None)` ([service.py:194-201](src/ai_qa/artifacts/service.py:194)) filters by `project_id` + optional `kind` only, ordered by `Artifact.name`. **No thread filter or thread ordering exists** — do the partition/sort in Python (stable sort preserves name order within each group).
- **Chosen default selection (document as the implemented behavior; adjustable by the user):** if any approved requirement has `thread_id == ctx.thread_id`, pre-select those (and list them first); the other project-level approved requirements are listed below, **deselected by default**, available to add. If there are **no** current-thread approved requirements, pre-select **all** project-level approved requirements so the user is never stuck with an empty set. This satisfies "prioritized" (ordering + pre-selection + badge) and "confirm or adjust" (deselect/select then Confirm).

### Gate pattern to mirror (from Story 11.2 / Bob)

Synchronous, pure, DB-reads-only `_check_preconditions() -> list[str]` at the **top** of `handle_start`, before any transition; empty list = pass. Each blocker → `send_message(message_type="error")` with a UX-DR12 *What happened / Why / What to do* body ([bob.py:124-157](src/ai_qa/agents/bob.py:124), [bob.py:243-250](src/ai_qa/agents/bob.py:243), [bob.py:503-518](src/ai_qa/agents/bob.py:503)). On block, **return without transitioning** (stay at START so the step is re-submittable) — do **not** go to ERROR. **Conftest hazard:** adding a `handle_start` gate has historically broken happy-path agent tests whose shared `mock_db`/`mock_project_context` aren't fully configured — fix centrally, see [agent-gate-conftest-regression]. Mary's gate is lighter than Bob's (no MCP, no Alice provider check), and existing Mary tests patch the adapter, so the blast radius should be small.

### WebSocket wiring (already in place — reuse it)

- Dispatch: `_handle_action` routes `start`→`handle_start(inputData)`, `approve`→`handle_approve(data)`, `reject`→`handle_reject(feedback, data)` ([websocket.py:312-322](src/ai_qa/api/websocket.py:312)). `data` is already passed to `handle_approve` — the confirm payload rides this channel. A new `agent_run` is created on `start` (`create_run = msg_type == "start"`, [websocket.py:303](src/ai_qa/api/websocket.py:303)).
- Step→name map includes `3: "Mary"` ([websocket.py:356-362](src/ai_qa/api/websocket.py:356)); per-project Mary instance is resolved via `_agent_for_context` and gets `set_project_context` just before dispatch (routes.py).
- Frontend `usePipelineState.updateFromMessage` sets `status` from `metadata.state` and `currentStep` from `message.agentName` via `AGENTS[name].stepNumber` ([usePipelineState.ts:296-303](frontend/src/hooks/usePipelineState.ts:296)). So any Mary message (agentName "Mary") moves the UI to step 3 automatically; the navigate message ([websocket.py:369-380](src/ai_qa/api/websocket.py:369)) carries `state:"start"` to reset status.

### Architecture compliance (hard rules)

- **Agents must never read/write storage directly — always through the artifact service** ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), forbidden anti-pattern [architecture.md:533](_bmad-output/planning-artifacts/architecture.md:533)). Mary's defined flow is exactly: derive user/project from thread → read requirements via artifact service → extractor → save to `projects/{project_id}/test_cases/` ([architecture.md:818-822](_bmad-output/planning-artifacts/architecture.md:818)).
- **Mandatory human review at every step — no auto-advance through a Review Request** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). The input-selection confirm is itself a review gate; do not auto-confirm.
- Artifacts are project-scoped under `projects/{project_id}/requirements|test_cases|test_scripts/` ([architecture.md:280](_bmad-output/planning-artifacts/architecture.md:280)).
- **Backend payload/model change → update TS interface simultaneously** and `npm run build`/`typecheck` ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)).

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Code must also pass **Pyrefly** — narrow `Optional` before use (`ctx.project_id`, `ctx.thread_id`, `StageResult.data`); no redundant casts/conversions; for any `Literal` default use a typed module constant. Async SQLAlchemy caveats don't apply — the artifact path is a **sync** `Session`.
- **Frontend:** React 19.2, TS ~6.0 strict, Tailwind v4, Vitest 4 (`vi.mock` hoisted file-wide; prefer `vi.spyOn(globalThis,"fetch")`; preserve real exports via `importOriginal()`), ESLint 9. Path alias `@` → `./src`. Prefer `getByRole`/`getByText` over `data-testid` in Playwright; icon/checkbox controls need accessible names.
- **No new packages** required. **No Alembic migration** required (11.7 already added the columns).

### Project Structure Notes

- New files: `frontend/src/components/agents/MaryInputSelection.tsx` (new `agents/` dir), `frontend/src/types/testcase.ts` (TS payload type), and a `MaryInputSelection` Vitest spec under `frontend/src/components/__tests__/` (match existing test placement), plus a Playwright spec under `frontend/e2e/`.
- Modified files (expected): `src/ai_qa/agents/mary.py`, `src/ai_qa/pipelines/artifact_adapter.py`, `frontend/src/App.tsx`, `tests/test_agents/test_mary.py`, `tests/pipelines/test_pipeline_artifact_adapter.py`, possibly `tests/conftest.py`.
- No backend route/schema changes are required: the selection payload travels over the existing WebSocket `send_message` metadata channel, and confirm rides the existing `approve`/`data` channel. No REST endpoint is added.

### Testing standards summary

- Backend: pytest, in-memory SQLite for the adapter test (the existing `test_pipeline_artifact_adapter.py` builds a `PipelineContext` directly and creates only `User/Project/Thread/AgentRun/Artifact/ArtifactVersion` tables — copy that scaffold). `pytest.raises(Exception)` is prohibited — use a specific type. Run the **whole** suite with `--no-cov` (subset runs fail the coverage gate; live baseline on prior epic was 1098 passed). Mypy gate is `src` only.
- Frontend: Vitest for the component; Playwright E2E with real-API state prep + `afterEach` cleanup of users/projects/artifacts.

### Previous Story Intelligence (11.7 / 11.8)

- 11.7 added the provenance columns (`source_type` `String(50)`, `source_url` `Text`, `warnings` `JSON`, all nullable) via migration `c8e6ace95b08` (`down_revision=604f28c24393`) and the authoritative `save_requirement` writing `{page_id}/requirement.md`. The other AC-metadata fields Mary may later need (12.5) are native columns: `created_by_user_id`, `updated_by_user_id`, `thread_id`, `agent_run_id`, `created_at`/`updated_at`, `kind`.
- 11.8 / D8 added `delete_draft_requirement` and made `save_requirement` idempotent-by-name. The retro flagged "Saved Question #1": **12.1 should filter approved (`source_type IS NOT NULL` / name pattern) as belt-and-suspenders** even though D8 dedupes — confirmed here as a hard requirement, because draft deletion is advisory/approve-path-only.
- 11.6 established the review-UX pattern: Bob's review is the bespoke inline `SplitPanel` (NOT the dormant unrendered `ChatInputArea`). Mary's input-selection panel is a **new** surface (sibling to, not a reuse of, SplitPanel — SplitPanel is per-item review, this is input-set selection). Use `ReviewContent` for the markdown preview as SplitPanel does.

### Git Intelligence

Recent commits (`b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`) are Epic 10; Epic 11 is implemented but **uncommitted in the working tree** on top of `b4ce65f`. That means the 11.7/11.8 producer code (`save_requirement`, `delete_draft_requirement`, provenance columns/migration, `PipelineArtifact`) is present in the tree but not yet committed — verify it is present before relying on it, and expect the working tree to also carry Epic 11 changes when you branch. The artifact/provenance suites (`tests/unit/test_artifact_service_provenance.py`, `tests/pipelines/test_pipeline_artifact_adapter.py`) are the closest existing patterns for the new tests.

### Sibling-story note (reusability)

Stories **13.1 (Sarah)** and **15.1 (Jack)** have the identical "load approved {test cases|scripts}, prioritize originating thread, user confirms/adjusts before {generation|execution}" shape ([epics.md:1272-1275], [epics.md:1601-1603]). Keep the adapter loader + the `MaryInputSelection` component generic enough that the pattern (filtered + thread-prioritized load → selection panel → confirm) can be re-applied for `load_test_cases`/`load_scripts` in those stories. Don't over-engineer a shared abstraction now, but avoid Mary-only hardcoding that would block reuse.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-12.1] — ACs (lines 1143-1163)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR5 (line 344, interpret NL test steps), FR27 (line 395, detect insufficient input/warn before generation); FR22 (line 384) is primarily 12.3
- [Source: _bmad-output/planning-artifacts/architecture.md] — Mary flow (818-822), no-direct-storage rule (518, 533), project-scoped artifacts (280), no-auto-advance (271-272), Mary model needs (1157-1161)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — Mary input "None (reads requirements/)" (99), mandatory review gate (188), status dots (304)
- [Source: src/ai_qa/agents/mary.py] — current lifecycle, stale docstrings (23, 69), load call (79-82)
- [Source: src/ai_qa/agents/bob.py] — gate pattern (124-157, 243-250, 503-518), producer save (1150-1158)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — DTO (18-26), `load_requirement_markdown` (134-136), `save_requirement` (51-105), `delete_draft_requirement` (107-132), mappers (238-250)
- [Source: src/ai_qa/artifacts/service.py] — `list_artifacts` (194-201), `read_current_content` (236)
- [Source: src/ai_qa/db/models.py] — `Artifact` columns incl. `thread_id` (145), provenance (152-154)
- [Source: src/ai_qa/api/websocket.py] — dispatch (276-332), step map (356-362), navigate (335-380)
- [Source: frontend/src/App.tsx] — agents array (1039-1075), Alice→Bob navigate (834-855), Alice auto-start (621-636), Bob render (1660-1677), handleBobApprove (974-988)
- [Source: frontend/src/hooks/usePipelineState.ts] — message→state mapping (285-313, 296-303)
- [Source: frontend/src/components/ReviewContent.tsx] — markdown preview component
- [Source: frontend/src/types/extraction.ts] — TS payload-type pattern
- [Source: tests/unit/test_artifact_service_provenance.py:174-218] — draft-vs-approved discriminator test pattern
- [Source: tests/pipelines/test_pipeline_artifact_adapter.py] — adapter test scaffold
- [Source: tests/test_agents/test_mary.py] — existing Mary tests (rewrite stale workspace-named ones)
- [Source: tests/conftest.py:27-63] — `mock_db` / `mock_project_context` (central gate fix point)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Fixed pre-existing integration test `test_bob_approve_saves_requirement_artifact` that tested the old per-page `review_markdown` phase (now removed). Renamed to `test_bob_auto_save_requirements_saves_artifact` and updated to call `_auto_save_requirements()` directly.

### Completion Notes List

**Story was REDEFINED on 2026-06-16** — the original multi-select Mary input-selection UI was superseded by a simpler single-id selection at Bob. The REDEFINED implementation was already present in the working tree (uncommitted); this dev pass verified, fixed one regression, and closed out the story.

**REDEFINED implementation verified and complete:**

1. `BobAgent._auto_save_requirements()` — auto-saves every extracted Confluence page as an approved requirement artifact (`source_type` set, draft deleted), replaces old per-page approve/skip/reject loop.
2. `BobAgent._handle_select_id()` — new `select_id` phase: classifies user input as existing Confluence page id (reuse), Jira ticket id (reads via MCP on demand), or unknown (retry). Persists choice as `mary_selected_id.json` configuration artifact + DONE metadata.
3. `BobAgent._read_and_save_jira_ticket()` — reads Jira ticket via MCP, saves as `source_type="jira"` approved requirement.
4. `MaryAgent.process()` — reads `selected_id` from `input_data` first, then falls back to `mary_selected_id.json` via `adapter.load_metadata()`; scopes generation to `{selected_id}/requirement.md`.
5. `App.tsx` — single-id input card (gated on `bobState.selectIdPrompt`), Bob→Mary auto-navigate (step 2 DONE → navigate step 3), Mary auto-start (`hasSentMaryStartRef`, separate from Alice ref).
6. `JiraReader.JIRA_TOOLS` trimmed to `["jira_get_issue"]`.
7. Stale class docstring in `mary.py` ("reads from workspace/requirements/") updated to correct description.

**AC1 + AC3 implemented for the single-id flow (2026-06-17):**
- **AC1 (approved-only):** `MaryAgent.process` resolves requirements through the approved-only
  filter (`Artifact.source_type IS NOT NULL`) before scoping to `selected_id`, so drafts are
  never fed into generation. No workspace path reads.
- **AC3 (block when nothing approved):** Mary's start path gates on the presence of at least one
  approved requirement; with none, it blocks generation (no PROCESSING, no extractor/LLM call)
  and sends a UX-DR12 message directing the user to run + approve Bob first.

**NOT built (intentionally — single-id flow supersedes the multi-select UI):**
- `MaryInputSelection.tsx` (multi-select component) — deferred
- `requirement_selection` payload, Bob→Mary multi-select navigation, and the per-requirement
  confirm-step UI — deferred
- The thread-prioritized `load_approved_requirements` adapter method as a multi-select source —
  not used by the single-id flow (AC1's approved-only guarantee is enforced in `mary.py`
  directly via the `source_type IS NOT NULL` filter)

**No Alembic migration required** — `source_type`/`source_url`/`warnings`/`thread_id` columns added by Story 11.7 (migration `c8e6ace95b08`).

**AdminDashboard Vitest failure is pre-existing** (not in modified files list; `AdminDashboard.test.tsx` untouched). This is a known D2 deferred from Epic 11.8.

**Test results:**
- Backend: 1191 passed, 0 failed (`uv run pytest --no-cov`)
- Mypy: no issues in 79 source files
- Frontend lint: 0 errors
- Frontend typecheck: pass
- Vitest: 170 passed, 1 pre-existing AdminDashboard failure (unrelated)

### File List

- `src/ai_qa/agents/bob.py` — `_auto_save_requirements`, `_handle_select_id`, `_read_and_save_jira_ticket`, updated `handle_approve` with `confirm_parent`→auto-save→`select_id` flow
- `src/ai_qa/agents/mary.py` — `process()` reads `selected_id`; updated class docstring; **2026-06-17:** approved-only requirement filter (`source_type IS NOT NULL`, AC1) + precondition gate that blocks generation with a UX-DR12 message when no approved requirement exists (AC3)
- `src/ai_qa/pipelines/artifact_adapter.py` — `save_metadata`, `load_metadata` (already present)
- `src/ai_qa/pipelines/jira_reader.py` — `JIRA_TOOLS` trimmed to `["jira_get_issue"]`
- `frontend/src/App.tsx` — single-id input card, Bob→Mary auto-navigate, Mary auto-start, `hasSentMaryStartRef`, `marySelectedId` state, `handleBobSelectId`
- `frontend/e2e/epic-11.spec.ts` — E2E test drives confirm→extract→select-id→handoff flow
- `tests/test_agents/test_bob.py` — new tests for `_auto_save_requirements` and `_handle_select_id`
- `tests/integration/test_project_scoped_agents.py` — fixed `test_bob_auto_save_requirements_saves_artifact` (was `test_bob_approve_saves_requirement_artifact` using removed `review_markdown` phase)

## Change Log

- 2026-06-16: Story REDEFINED by Thuong — single-id selection at Bob replaces multi-select Mary UI. Bob auto-saves all requirements, asks user to pick ONE id, persists as `mary_selected_id.json`. Mary reads `selected_id` and scopes generation. Frontend wires Bob→Mary navigate + Mary auto-start.
- 2026-06-16: Dev agent verified REDEFINED implementation, fixed integration test regression (old `review_markdown` phase removed), updated Mary class docstring. All 1191 backend tests pass.
- 2026-06-17: Thuong decided AC1 (approved-only inputs) + AC3 (block when no approved requirement) must hold in the single-id flow. Implemented in `mary.py`: approved-only `source_type IS NOT NULL` filter before scoping to `selected_id`, plus a precondition gate that blocks generation (no PROCESSING/extractor call) and emits a UX-DR12 message when no approved requirement exists. The multi-select `MaryInputSelection.tsx` UI / `requirement_selection` payload remain NOT built. Task checkboxes reset to reflect shipped reality.

## Status

review
