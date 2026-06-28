---
baseline_commit: 79f3f3c
---

# Story 13.7: Script Approval, Rejection, and Regeneration

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want to **approve, reject, or regenerate** generated Playwright scripts with feedback — where **approval records who approved and when**, **rejection feeds my feedback back into regeneration** (revising the affected script where possible), and **only approved scripts are eligible for execution by Jack** —
so that only reviewed scripts become executable, and rejected/unapproved scripts are never run.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.7](_bmad-output/planning-artifacts/epics.md) (lines 1389-1409), expanded with implementation defaults (see "Scope decisions" — **all four defaults CONFIRMED by Thuong 2026-06-13** ("áp dụng default"); no pending input remains, see "Confirmed decisions" at the end of this file). This is the **approve/reject/regenerate SEMANTICS layer** for Sarah — the script analog of **Story 12.4** (Mary's approve/reject/regenerate + `approved_by`/`approved_at` stamping on the `TestCase` model) and of **Bob's 11.6** reject-regenerate path. It sits **on top of** Story 13.5's review panel + present-all transport + index-addressable handlers and Story 13.6's edit+validate gate. It does **not** build a UI panel — it refines the behavior of the handlers 13.5/13.6 already made index-addressable.

### AC1 — Approve → eligible for Jack + approval metadata (user + timestamp)

- **Given** a generated script is reviewed
- **When** the user approves it
- **Then** the script becomes **eligible for Jack execution** (its `approved` flag is the structural eligibility discriminator — see AC3 + Dev Notes "Jack-eligibility")
- **And** approval metadata records **user and timestamp** — `approved_by` (the approving user) + `approved_at` (ISO-8601) stamped on the `GeneratedScript` and surfaced in the review payload + the panel

### AC2 — Reject with feedback → regenerate/revise where possible; rejected not eligible

- **Given** the user rejects a script with feedback
- **When** feedback is submitted
- **Then** Sarah **regenerates or revises the affected script where possible** — the rejection feedback is fed into the regeneration so the new script reflects it (where the generator can act on it; see Dev Notes "Feedback-into-regeneration")
- **And** the rejected (and any regenerated-not-yet-reapproved) script is **not available for Jack execution** — its `approved`/`approved_by`/`approved_at` are cleared, so it is excluded until explicitly re-approved

### AC3 — Unapproved → excluded from Jack execution input

- **Given** a script remains unapproved (rejected, skipped, regenerated-not-reapproved, or never reviewed)
- **When** Jack requests executable scripts for the selected project
- **Then** that script is **excluded from execution input** — this is satisfied **structurally + by contract**: only approved scripts are persisted to `projects/{id}/test_scripts/`, and the `approved` flag/metadata is the discriminator a future **Story 15.1** (Jack input selection) filters on (see Dev Notes "Jack-eligibility is structural"). 13.7 owns the producer-side guarantee (unapproved scripts are never marked/persisted as approved); Jack's consumer-side query is **Epic 15**, out of scope here

---

## ⚠️ Sequencing dependency (READ FIRST — critical)

**Story 13.7 is near the top of the Sarah review chain. It REFINES — it does not create — the review handlers, the transport, and the `GeneratedScript` model.** Hard chain: **13.1 → 13.2 → 13.3 → 13.4 → 13.5 → 13.6 → 13.7 → 13.8.** Prerequisites (verified absent at `79f3f3c` — see "Verification at baseline" below):

1. **Story 13.1 (Sarah step-4 surface + phase-dispatched lifecycle).** Adds `isSarahStep`/`sarahState`/`handleSarahMessage` in [App.tsx](frontend/src/App.tsx), and the **phase-dispatched** `handle_approve` (`self.phase` = `"input_selection"` vs `"script_review"`) + `confirmed_test_cases` in [sarah.py](src/ai_qa/agents/sarah.py). 13.7's backend edits live in the **script-review branch** of that phase-dispatched handler. If `self.phase`/`sarahState`/`handleSarahMessage` are absent → **13.1 unmerged → flag and stop.**
2. **Story 13.5 (panel + present-all transport + index-addressable handlers + `_reviewed_indices`).** Builds `frontend/src/components/agents/SarahScriptReviewPanel.tsx`, `SarahAgent._present_script_review` (`metadata.type == "script_review"` + `scripts[]`), the TS `ScriptReviewItem`/`ScriptReviewPayload` types, and **index-addressable** `handle_approve`/`handle_reject`/`handle_skip` keyed off a `_reviewed_indices: set[int]` DONE gate. **13.5 already: (a) marks `approved=True` + saves on approve; (b) clears the `approved` flag + regenerates on reject; (c) re-emits the present-all payload.** 13.7 layers the **approval metadata stamp** (AC1), the **feedback-into-regeneration** (AC2), and the **`approved_by`/`approved_at` clearing on reject/regenerate** (AC3) on top. If `SarahScriptReviewPanel`/`_present_script_review`/`_reviewed_indices` are absent → **13.5 unmerged → flag and stop.**
3. **Story 13.6 (edit + validate).** Adds the editable right pane + the `validate_script` gate inside the **same** script-review branch of `handle_approve` (edit → validate → on pass set `script.script_content = edited` → save). **13.7's approval stamp lands at/after that save** (it stamps regardless of whether the content was edited — the stamp is orthogonal to the edit gate). If `validate_script`/`script_validation_error` are absent → **13.6 unmerged → flag and stop** (do NOT re-implement the edit/validate here).
4. **Story 13.2 + Epic 12** (the `GeneratedScript.warnings` channel, Mary's approved test cases, `frontend/src/components/agents/`, `frontend/src/types/testcase.ts` + `ScriptReviewItem`). 13.7 does not change `warnings` but extends the same `GeneratedScript` model + `ScriptReviewItem` type. Verify present; reconcile and note divergence.

### Verification at baseline (`79f3f3c`)

Confirmed at this commit: **NONE of 12.1–12.5 or 13.1–13.6 are in the working tree** — no `isSarahStep`/`sarahState`/`handleSarahMessage`/`script_review`/`SarahScriptReviewPanel`/`_reviewed_indices` anywhere in `frontend/src` or `src`; the live `sarah.py` `handle_approve` ([sarah.py:519-570](src/ai_qa/agents/sarah.py:519)) accepts but **ignores** `data`, saves the **original** `script_content`, advances `_current_review_index` linearly, and is **not** phase-dispatched; `handle_reject` ([sarah.py:572-619](src/ai_qa/agents/sarah.py:572)) regenerates but does **not** wire feedback into the prompt and does **not** clear an `approved` flag; `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) has **no** `warnings`/`approved_by`/`approved_at`. **13.7 is therefore blocked until 13.1–13.6 land.** Before starting, verify the prerequisites in the **live (13.1–13.6-merged) tree** (Task 0); if unmerged, **flag and stop** — do NOT re-implement upstream. Treat any cited `file:line` / before-after snippet in this story as a **lead to verify against the live code**, not gospel — reconcile and record divergences in Completion Notes ([verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md), [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## Scope decisions (CONFIRMED — Thuong locked all four defaults 2026-06-13: "áp dụng default")

Chosen from the code + ACs + planning docs + the **12.4 / 11.6** sibling precedent, and **confirmed by Thuong** ("áp dụng default", 2026-06-13). The four formerly-open forks are now resolved decisions (full list under "Confirmed decisions" at the end of this file). No pending input — the dev agent implements exactly as written.

- **This is the approve/reject/regenerate SEMANTICS story for Sarah — the script analog of Mary's 12.4.** 13.5 built the panel + transport + index-addressable handlers and **preserved** the Epic-5 behavior (save on approve, regenerate on reject, advance, DONE). 13.6 added edit + validation. **13.7 refines the *semantics*:** (a) **AC1** — add `approved_by`/`approved_at` to `GeneratedScript`, stamp them when a script is approved, surface them in the present-all payload + TS type + panel; (b) **AC2** — wire the rejection **feedback into regeneration** (extend `ScriptGenerator.generate`/`_generate_single_script` with an optional `feedback` param injected into the prompt — the substance 13.5 explicitly deferred to 13.7), and ensure a rejected/regenerated script's approval is cleared; (c) **AC3** — establish the `approved` flag as the structural Jack-eligibility discriminator and guarantee unapproved scripts are never marked/persisted as approved. The **bulk** of the work is backend (`sarah.py` + `script_generator.py`); the frontend change is small (surface `approved_by`/`approved_at` in `ScriptReviewItem` + the panel's per-item status). (CONFIRMED — Q#1, Q#2.)
- **AC1 approval recording is 13.7; the artifact-save metadata expansion + idempotency + `.spec.ts` fix is 13.8 (strict 12.4→12.5 mirror).** 13.7 stamps `approved_by`/`approved_at` on the **in-memory `GeneratedScript`** (mirroring 12.4 stamping on the `TestCase` model) and surfaces them in the review payload + panel. **13.8** lifts those (plus source test case artifact ID, output/logical path, approval status, creator, updater, originating thread, originating agent run, validation status) into the **durable** artifact-save metadata/sidecar and owns save idempotency + the `.spec.ts` fallback defect. **Key difference from Mary:** a `TestCase` is saved as `model_dump_json` (so 12.4's stamp persists automatically), but a **script is saved as raw `.py` text** ([artifact_adapter.py:143-145](src/ai_qa/pipelines/artifact_adapter.py:143)) — so `GeneratedScript.approved_by`/`approved_at` do **not** auto-persist through `save_script`; their **durable** home is the metadata sidecar, which is **13.8's** to expand. 13.7's AC1 is satisfied by stamping the model + surfacing it (recorded in review state + UI); the durable artifact-metadata persistence is **13.8**. Do **not** expand `_write_approved_scripts_metadata` here. (CONFIRMED — Q#2: durable lift stays in 13.8.)
- **AC2 "regenerate or revise where possible" = wire feedback into the prompt.** The live regenerate path (`_regenerate_current_script` → `ScriptGenerator.generate`) **drops the feedback** ([sarah.py:412-414](src/ai_qa/agents/sarah.py:412): "feedback is not yet supported by ScriptGenerator"). 13.5 preserved that same-prompt re-run and **deferred feedback-into-the-prompt to 13.7**. Add an optional `feedback: str | None = None` to `ScriptGenerator.generate(...)` → `_generate_single_script(...)` and inject it into the generation prompt (mirror Bob's `RequirementFormatter.convert_page(page, feedback=...)` from 11.6 and Mary's feedback-regen from 12.4), so the regenerated script reflects the reviewer's correction. The existing replace-at-index + re-present behavior (13.5) stays; only the prompt gains the feedback. "Where possible" = if the generator/LLM is unavailable or errors, fall back to the existing same-prompt re-run + the existing error message. (CONFIRMED — Q#1: wire feedback into the prompt; the same-prompt-re-run-only alternative is rejected.)
- **AC3 Jack-eligibility = structural + contract (no Jack code).** Jack is **Epic 15** (`backlog`, not started). The faithful 13.7 contribution: the `approved` flag is the eligibility discriminator; `save_script` runs **only on approve** so only approved script **content** reaches `kind="playwright_script"` → `test_scripts/`; reject/skip/regenerate never mark a script approved (and clear any prior stamp). **Story 15.1** (Jack — approved-script input selection, the analog of 13.1's `load_approved_test_cases`) will add a `load_approved_scripts` loader that filters on this. 13.7 writes **no** Jack code and adds **no** loader. Document the contract in Completion Notes + a code comment so 15.1 inherits it cleanly. (CONFIRMED — Q#3: do NOT pre-build the `load_approved_scripts` seam; leave it to 15.1.)
- **E2E coverage = scoped (same rationale as 13.5/13.6).** Primary guardrails: **backend pytest** on the stamp-on-approve, clear-on-reject, feedback-into-regeneration, and structural-eligibility paths; **Vitest** on the panel surfacing `approved_by`/`approved_at`. Playwright E2E is scoped because LLM-driven generation is not E2E-reproducible without a provider key and `page.route` mocking is forbidden ([project-context.md#Testing-Rules](project-context.md)); the chrome-path FE is deferred (13.1). (CONFIRMED — Q#4: scoped E2E; full LLM-driven E2E rejected.)

### Boundary fences — what 13.7 does NOT do

- **Does NOT build or restructure the review panel, the present-all transport, the index-addressable handlers, or the `_reviewed_indices` DONE gate** — 13.5 owns those. 13.7 **extends** the script-review branch of `handle_approve`/`handle_reject` (adds the stamp / clears it / wires feedback) and adds two fields to the per-script payload entry + `ScriptReviewItem`.
- **Does NOT add the editable pane or the validation gate** — 13.6 owns `validate_script` + `script_validation_error` + the Edit tab + the per-index edits map. 13.7's stamp lands at/after 13.6's save and is independent of whether the content was edited.
- **Does NOT expand the artifact-save metadata, add save idempotency/D8 for scripts, fix the `.spec.ts` save-fallback ([sarah.py:538](src/ai_qa/agents/sarah.py:538)), or write a durable approval sidecar** — that is **Story 13.8**. 13.7 saves the approved content through the **existing** `save_script` call (unchanged) and stamps the model only.
- **Does NOT write Jack/Epic-15 code** — no `load_approved_scripts`, no execution input selection, no `JackAgent`. AC3 is a producer-side structural guarantee + a documented contract for 15.1.
- **Does NOT add warnings detectors or change the warnings channel / generation selectors / SSO handling / confidence engine** (13.2/13.3/13.4 + Epic-5). Feedback is injected into the prompt **only** for regeneration; the detectors and confidence float are untouched.
- **Does NOT change `handle_skip` semantics** beyond what 13.5 set (skip = "leave for Minh", not approved, recorded in `_reviewed_indices`). A skipped script is structurally unapproved (AC3) — no extra change needed.

## What ALREADY EXISTS (reuse / extend — do not recreate)

| Capability | Where it lives | Status / action for 13.7 |
| --- | --- | --- |
| `GeneratedScript` model (`test_case`/`script_content`/`file_path`/`confidence`/`approved`/`error_message`; **+ `warnings`** from 13.2) | [sarah.py:26-37](src/ai_qa/agents/sarah.py:26) | ⚠️ **EXTEND** — add `approved_by: str \| None = None` + `approved_at: str \| None = None` |
| `handle_approve` script-review branch — phase-dispatched (13.1), index-addressable (13.5), edit+validate (13.6), saves via `save_script`, `_reviewed_indices` DONE gate | 13.6's version of [sarah.py:519-570](src/ai_qa/agents/sarah.py:519) | ⚠️ **EXTEND** — after the (13.6) save, stamp `approved_by = ctx.user_email or str(ctx.user_id)` + `approved_at = datetime.now(UTC).isoformat()` on the approved script |
| `handle_reject` script-review branch — index-addressable (13.5): clears `approved`, sets `_current_review_index = index`, regenerates via `process(feedback=...)`, clears `index` from `_reviewed_indices`, re-emits | 13.5's version of [sarah.py:572-619](src/ai_qa/agents/sarah.py:572) | ⚠️ **EXTEND** — also clear `approved_by`/`approved_at` (AC3); ensure feedback reaches regeneration (AC2) |
| `_regenerate_current_script(feedback)` — re-runs `ScriptGenerator.generate` but **drops feedback** (`# feedback not yet supported`) | [sarah.py:373-454](src/ai_qa/agents/sarah.py:373) (drop at 412-414) | ⚠️ **EXTEND** — pass `feedback` through to `generate(...)` (AC2) |
| `ScriptGenerator.generate(test_cases, target_url)` → `_generate_single_script` → LLM prompt | [script_generator.py:64-68](src/ai_qa/pipelines/script_generator.py:64), single-script + prompt builders | ⚠️ **EXTEND** — add optional `feedback: str \| None = None`, thread it to `_generate_single_script` + into the prompt |
| `_present_script_review` per-script entry (13.5): `index`/`test_case`/`script_content`/`script_language`/`file_path`/`confidence`/`warnings`/`approved`/`status`/`error_message` | 13.5's `_present_script_review` (replaces [sarah.py:698-736](src/ai_qa/agents/sarah.py:698)) | ⚠️ **EXTEND** — add `approved_by`/`approved_at` to each entry (surface AC1 in the UI) |
| `ScriptReviewItem` TS interface (13.5) | 13.5's `frontend/src/types/testcase.ts` or `script.ts` | ⚠️ **EXTEND** — add `approved_by?: string \| null; approved_at?: string \| null` (full-stack sync) |
| `SarahScriptReviewPanel` per-item status indicator (13.5) | 13.5's `frontend/src/components/agents/SarahScriptReviewPanel.tsx` | ⚠️ **EXTEND** — when a script is `approved`, show "Approved by {approved_by} · {approved_at}" near the status pill |
| `PipelineContext.user_email: str` / `user_id: UUID` (the approving user) | [context.py:15-16](src/ai_qa/pipelines/context.py:15) | ✅ **reuse** — `approved_by = ctx.user_email or str(ctx.user_id)` (narrow `project_context is not None` first) |
| `from datetime import UTC, datetime` + `datetime.now(UTC).isoformat()` timestamp pattern | [alice.py:25,996](src/ai_qa/agents/alice.py:25), [bob.py:2,1177](src/ai_qa/agents/bob.py:2) | ✅ **mirror** — same import + call for `approved_at` |
| `PipelineArtifactAdapter.save_script(name, content)` → `kind="playwright_script"` → `test_scripts/` (runs **only on approve**) | [artifact_adapter.py:143-145](src/ai_qa/pipelines/artifact_adapter.py:143), [storage.py:34-35](src/ai_qa/artifacts/storage.py:34) | ✅ **reuse unchanged** — the structural basis of AC3 (only approved content persisted); do NOT add D8/idempotency (13.8) |
| `_write_approved_scripts_metadata` — per-script sidecar (`source_url`/`model`/`confidence`/`test_case_title`), written on DONE | [sarah.py:738-756](src/ai_qa/agents/sarah.py:738) | ⛔ **do NOT expand** — 13.8 lifts `approved_by`/`approved_at` + approval status + source ID + validation status here |
| WebSocket dispatch: `approve`→`handle_approve(data)`, `reject`→`handle_reject(feedback, data)` (full `data` passthrough; `script_index` rides it per 13.5) | [websocket.py:312-322](src/ai_qa/api/websocket.py:312) | ✅ **reuse** — no router/REST/schema change |
| 12.4's `TestCase.approved_by`/`approved_at` stamping pattern + the 12.4↔12.5 boundary | [12-4-mary-review-workflow.md](_bmad-output/implementation-artifacts/12-4-mary-review-workflow.md) (its Task 2 + its 12.4↔12.5 boundary note) | ✅ **mirror exactly** — Sarah's `GeneratedScript` stamp = Mary's `TestCase` stamp; 13.8 = Mary's 12.5 |

---

## Tasks / Subtasks

- [x] **Task 0 — Confirm prerequisites (BLOCKING gate)**
  - [x] Verify **13.1** merged: `self.phase`/`confirmed_test_cases` + phase-dispatched `handle_approve` in [sarah.py](src/ai_qa/agents/sarah.py); `isSarahStep`/`sarahState`/`handleSarahMessage` in [App.tsx](frontend/src/App.tsx). If absent → **flag and stop.**
  - [x] Verify **13.5** merged: `SarahScriptReviewPanel.tsx` exists; `_present_script_review` emits `metadata.type == "script_review"` with `scripts[]`; `handle_approve`/`handle_reject`/`handle_skip` read `data["script_index"]`; `self._reviewed_indices: set[int]` gates DONE; `handle_reject` already clears `approved` + regenerates + re-emits. If absent → **flag and stop** (do NOT build the panel/transport).
  - [x] Verify **13.6** merged: `validate_script`/`script_validation_error`/the Edit tab exist; `handle_approve`'s script-review branch has the edit→validate→save step. If absent → **flag and stop** (do NOT re-implement edit/validate).
  - [x] Verify **13.2 + Epic 12**: `GeneratedScript.warnings`, `ScriptReviewItem` TS type, `frontend/src/types/testcase.ts`, `frontend/src/components/agents/`. Record verification + any divergence (field names, prop shapes, the exact shape of the 13.5/13.6 `handle_approve` branch) in Completion Notes **before** relying on them.
  - [x] **13.3/13.4 need no separate 13.7 check** — they specialize the `warnings` channel that 13.2 establishes, and 13.7 touches only the 13.2-established `warnings`/`GeneratedScript`/`ScriptReviewItem` surface (not the selector/assertion or SSO detectors). They are transitive prerequisites of 13.5/13.6, so a merged 13.5/13.6 implies them. The full chain is listed for sequence completeness.

- [x] **Task 1 — Backend: approval metadata on `GeneratedScript` (AC1)**
  - [x] In `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) append, with backward-compatible defaults: `approved_by: str | None = None` and `approved_at: str | None = None`. Update the class docstring. (No migration — `GeneratedScript` is an in-memory Pydantic model, not a DB table; the script persists as raw text.)
  - [x] Add `from datetime import UTC, datetime` to the imports (mirror [bob.py:2](src/ai_qa/agents/bob.py:2) / [alice.py:25](src/ai_qa/agents/alice.py:25)).
  - [x] In the **script-review branch** of (13.1-phase-dispatched, 13.5-index-addressable, 13.6-edit+validate) `handle_approve`, **after** the existing save (13.6 sets `script.script_content = edited` on a passing validate, then `save_script(...)`; on the back-compat no-edit path it saves the original), stamp the just-approved script:

    ```python
    # AC1: record who approved and when. Mirrors 12.4's TestCase stamp.
    assert self.project_context is not None  # narrowed; SarahAgent requires it
    script.approved_by = self.project_context.user_email or str(self.project_context.user_id)
    script.approved_at = datetime.now(UTC).isoformat()
    # --- 13.5's _reviewed_indices.add(index) + DONE gate continue unchanged ---
    ```

  - [x] Stamp **only** on the success path (after a passing validate + save). Do **not** stamp on the 13.6 validation-failure early-return path (that path saves nothing and stays REVIEW_REQUEST). Preserve the 13.5 `_reviewed_indices` DONE gate, the `_write_approved_scripts_metadata()` call on DONE, and the success message.
  - [x] **Do NOT** expand `_write_approved_scripts_metadata` ([sarah.py:738-756](src/ai_qa/agents/sarah.py:738)) — leave the durable sidecar lift (`approved_by`/`approved_at` + approval status + source ID + validation status) to **13.8**. Note this boundary in Completion Notes.

- [x] **Task 2 — Backend: clear approval on reject/regenerate (AC2, AC3)**
  - [x] In the **script-review branch** of `handle_reject` (13.5's version: resolves `index = data.get("script_index", ...)`, clears the `approved` flag, sets `_current_review_index = index`, delegates to the regenerate path, clears `index` from `_reviewed_indices`, re-emits `_present_script_review`), also clear the **approval metadata** on the rejected script: `self._generated_scripts[index].approved_by = None` and `.approved_at = None`. A rejected script must never be treated as approved (AC3 "rejected output never approved").
  - [x] When `_regenerate_current_script` **replaces** the script at `_current_review_index` with a fresh `GeneratedScript(...)` ([sarah.py:423-428](src/ai_qa/agents/sarah.py:423)), the new instance gets the default `approved=False`/`approved_by=None`/`approved_at=None` — **verify** the replacement does not carry a stale stamp (it shouldn't, since it's a new object, but assert it in Task 7). A regenerated-not-reapproved script is unapproved → excluded from Jack (AC3).
  - [x] **Do NOT** change the 13.5 transport, the `_reviewed_indices` bookkeeping, or the re-present behavior — only add the two `= None` clears + ensure feedback flows (Task 3).

- [x] **Task 3 — Backend: feedback-into-regeneration (AC2)**
  - [x] Extend `ScriptGenerator.generate(self, test_cases, target_url=None)` ([script_generator.py:64-68](src/ai_qa/pipelines/script_generator.py:64)) with an optional `feedback: str | None = None`; thread it to `_generate_single_script(test_case, target_url, feedback=None)` and inject it into the LLM prompt (a clearly-delimited "Reviewer feedback to address in this revision: …" section). Keep it optional + backward-compatible (existing callers pass nothing → identical behavior).
  - [x] In `_regenerate_current_script(feedback)` ([sarah.py:373-454](src/ai_qa/agents/sarah.py:373)), pass the `feedback` through: `await script_generator.generate(test_cases=[test_case], target_url=self._target_url, feedback=feedback)`. Remove the stale `# Note: feedback is not yet supported` comment ([sarah.py:412-414](src/ai_qa/agents/sarah.py:412)).
  - [x] **"Where possible" fallback:** if the generator/LLM errors or `feedback` is empty, the existing same-prompt re-run + error handling stays (no regression). Sanitize/cap the feedback before prompt injection if a length cap exists for other prompts; never log the raw script body alongside feedback (security — Dev Notes).
  - [x] **CONFIRMED (Q#1): this task stands — wire feedback into the prompt.** The rejected alternative (keep the same-prompt re-run, acknowledge feedback in the chat message only, no `ScriptGenerator` change) is recorded under "Confirmed decisions"; do NOT implement it.

- [x] **Task 4 — Backend: surface approval metadata in the present-all payload (AC1, full-stack sync)**
  - [x] In 13.5's `_present_script_review` per-script entry, add `"approved_by": s.approved_by` and `"approved_at": s.approved_at` (alongside the existing `approved`/`status`/`warnings`/`confidence` keys). This carries AC1's recording to the client so the panel can show it.
  - [x] No new message type — rides the existing `script_review` payload (no router/schema change).

- [x] **Task 5 — Backend: AC3 structural-eligibility contract (AC3)**
  - [x] Add a code comment at `save_script`'s call site in `handle_approve` (and/or in a short docstring on the script-review branch) stating the contract: *"Only approved scripts are persisted to `test_scripts/` (`kind="playwright_script"`). The `approved` flag + `approved_by`/`approved_at` are the Jack-eligibility discriminator consumed by Story 15.1 (`load_approved_scripts`). Rejected/skipped/regenerated scripts are never marked or saved as approved."*
  - [x] **Verify** (no code change expected) that the skip path (13.5's `handle_skip`) does **not** call `save_script` and does **not** set `approved` — so skipped scripts are structurally excluded. If 13.5 left skip saving content, flag it (it should not). Record the verification in Completion Notes.
  - [x] **Do NOT** add `load_approved_scripts` or any Jack code (Epic 15; Q#3 confirmed — seam left to 15.1). Do NOT alter `_write_approved_scripts_metadata` (13.8).

- [x] **Task 6 — Frontend: TS type + panel surface for approval metadata (AC1, full-stack sync)**
  - [x] Extend 13.5's `ScriptReviewItem` (in `frontend/src/types/testcase.ts` or `script.ts`) with `approved_by?: string | null` and `approved_at?: string | null` — match the Task 4 payload **exactly** (full-stack-sync rule, [project-context.md#Critical-Don't-Miss-Rules](project-context.md)).
  - [x] In `SarahScriptReviewPanel`, when an item's `status === "approved"` (or `approved === true`), render a small caption near the status pill: `Approved by {approved_by} · {formatted approved_at}` (format the ISO timestamp readably; tolerate `null` → omit the caption). Color **+ text** (never color alone — [ux-design-specification.md:790](_bmad-output/planning-artifacts/ux-design-specification.md:790)). No new component; extend the existing per-item status rendering (13.5 Task 4).
  - [x] No new `App.tsx` handler is needed — `handleSarahApprove`/`handleSarahReject` (13.5/13.6) already send `script_index` (+ `script_content` from 13.6); the approval stamp is computed server-side from context. Confirm the reject handler threads `feedback` (it does — 13.5 `onReject(index, feedback)` → `sendMessage({type:"reject", step:4, feedback, data:{script_index:index}})`); the feedback now reaches the prompt (Task 3). If `handleSarahReject` does **not** forward `feedback` in the live tree, that means 13.5 is unmerged/incomplete → **flag and stop** (Task 0 should have caught it); do NOT add the forwarding here (it is 13.5-owned frontend wiring).

- [x] **Task 7 — Backend tests (AC1, AC2, AC3)**
  - [x] Extend `tests/test_agents/test_sarah.py` (seed `_generated_scripts` with `GeneratedScript(...)`, `agent.phase = "script_review"` per 13.1, patch `ai_qa.agents.sarah.PipelineArtifactAdapter` + `ScriptGenerator` — [test_sarah.py:172-212](tests/test_agents/test_sarah.py:172); assert via `mock_broadcast.call_args_list` → `call[0][0].metadata`):
    - **Approve stamps (AC1):** `handle_approve({action:"approved", script_index:0})` → `self._generated_scripts[0].approved is True`, `.approved_by == mock_project_context.user_email` (or `str(user_id)` fallback), `.approved_at` is a parseable ISO string; `0 in _reviewed_indices`; `save_script` called. With 13.6's edited path (`script_content` in data), the stamp still lands after the validate+save.
    - **Validation-failure does NOT stamp (13.6 preserved):** an invalid edited approve → no stamp set, `approved` stays `False`, `0 not in _reviewed_indices` (13.6 behavior intact).
    - **Reject clears stamp (AC2/AC3):** pre-set `_generated_scripts[0].approved=True`/`approved_by="x"`/`approved_at="t"`, then `handle_reject("fix the selector", {script_index:0})` → after regenerate, `approved is False`, `approved_by is None`, `approved_at is None`; `0 not in _reviewed_indices`; `script_review` re-emitted.
    - **Feedback reaches regeneration (AC2):** assert `ScriptGenerator.generate` was called with `feedback="fix the selector"` (patch/inspect the mock's call kwargs). (Q#1 confirmed → the feedback-in-prompt path is the one to assert; the rejected chat-message-only alternative is not implemented.)
    - **Eligibility is structural (AC3):** after a skip (`handle_skip`/skip-action, `script_index:1`), `save_script` was **not** called for index 1 and `_generated_scripts[1].approved is False`; the present-all payload shows `status=="skipped"` for it. (No Jack code asserted — Epic 15.)
    - **Payload carries the stamp (AC1):** after an approve, the re-emitted `script_review` per-script entry for the approved index has `approved_by`/`approved_at` populated.
  - [x] New/extended `tests/pipelines/test_script_generator.py`: `generate(..., feedback="…")` injects the feedback into the prompt (assert via the patched LLM client's call args or the built prompt string); `generate(...)` with no feedback is byte-identical to today (back-compat).
  - [x] **Regression:** the existing 13.5/13.6 approve/reject/skip/navigate tests still pass (stamp/clear/feedback are additive). Run the **whole** suite `uv run pytest --no-cov` (subset runs trip the coverage gate; prior-epic baseline = 1098 passed — [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). `uv run mypy src` clean. Fix shared-fixture breaks centrally in [tests/conftest.py](tests/conftest.py) ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).

- [x] **Task 8 — Frontend tests (AC1)**
  - [x] Extend `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx` (mirror [SplitPanel.test.tsx](frontend/src/components/__tests__/SplitPanel.test.tsx)): an item with `status:"approved"`, `approved_by:"qa@corp.vn"`, `approved_at:"2026-06-13T10:00:00+00:00"` renders the "Approved by qa@corp.vn …" caption (text, not color-only); a `pending`/`skipped` item does **not** render it; a `null` `approved_at` omits the caption gracefully. Reject still calls `onReject(index, feedback)`; Approve still calls `onApprove(index, editedContent?)` (13.6). Vitest 4 rules — [project-context.md#Testing-Rules](project-context.md) (`vi.mock` hoisted; non-null assert known array elements `scripts[i]!`).
  - [x] Playwright E2E (`frontend/e2e/epic-13.spec.ts`): **scope realistically** (Q#4 confirmed) — same constraints as 13.5/13.6. If the full path can't be seeded, scope to the deterministic surface (panel renders the approval caption from a seeded approved item) and env-gate the LLM legs (`test.skip(!providerKey, …)`); `afterEach` cleanup (delete project + user). Otherwise defer to Vitest and note it.

- [x] **Task 9 — Verify (no migration)**
  - [x] Backend: `uv run pytest --no-cov` green; `uv run mypy src` clean; Pyrefly-clean — narrow `self.project_context` (and `data.get("script_index")`) before use; `approved_by`/`approved_at` typed `str | None`; coerce `ctx.user_email or str(ctx.user_id)` (don't `str()` a value already `str`); no redundant casts/conversions; `from datetime import UTC, datetime`; `pytest.raises` needs a specific type + `match=`.
  - [x] Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest), E2E spec. Confirm **no new package** (`git status` on `frontend/package.json`/`package-lock.json`).
  - [x] Confirm **no Alembic migration** — `GeneratedScript` is an in-memory Pydantic model (not a DB table); the script persists as raw text via the existing `save_script`; approval recording rides the WS payload + (durably) 13.8's sidecar. State explicitly in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/sarah.py` — Epic-5 implementation; 13.1 phase-dispatches; 13.5 makes it present-all + index-addressable; 13.6 adds edit+validate; 13.7 adds the approval semantics.**

- **At baseline `79f3f3c`** (pre-13.x): `handle_approve` ([:519-570](src/ai_qa/agents/sarah.py:519)) marks `approved=True`, saves the **original** `script_content` via `save_script(Path(file_path).name or "<…>.spec.ts", …)` ([:537-540](src/ai_qa/agents/sarah.py:537)), advances `_current_review_index`, DONE at `>= len`; `handle_reject` ([:572-619](src/ai_qa/agents/sarah.py:572)) acknowledges + delegates to `process(self._start_input_data, feedback=...)` → `_regenerate_current_script` which **drops the feedback** ([:412-414](src/ai_qa/agents/sarah.py:412)) and does **not** clear an `approved` flag; `handle_skip` ([:621-666](src/ai_qa/agents/sarah.py:621)) advances without saving; `GeneratedScript` ([:26-37](src/ai_qa/agents/sarah.py:26)) has no `approved_by`/`approved_at`.
- **By the time 13.7 starts, 13.1+13.5+13.6 have changed this**: `handle_approve` is phase-dispatched (`self.phase`), the script-review branch reads `data["script_index"]`, validates `data["script_content"]` (13.6), saves the edited-or-original content, adds to `_reviewed_indices`, DONE when all reviewed; `handle_reject` is index-addressable, clears `approved`, regenerates, re-emits; present is `_present_script_review` (present-all). **13.7's insertions are surgical:** (Task 1) stamp `approved_by`/`approved_at` right after the 13.6 save; (Task 2) two `= None` clears in the reject branch; (Task 3) thread `feedback` into `generate`; (Task 4) two keys in the payload entry. Reconcile against the live (13.1/13.5/13.6-merged) shape; the snippets here show the *new* lines wrapped around **preserved** upstream behavior — **do not delete** the surrounding 13.5/13.6 logic ([create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

**`src/ai_qa/agents/mary.py` / Story 12.4 — the direct analog.** 12.4 adds `approved_by`/`approved_at` to the `TestCase` model and stamps the just-approved case in `handle_approve`'s per-item branch (`tc.approved_by = ctx.user_email or str(ctx.user_id)`, `tc.approved_at = datetime.now(UTC).isoformat()`), clears the stamp on regenerate (AC3 "rejected output never approved"), and leaves the durable artifact-save metadata lift to **12.5**. **13.7 is the same shape for Sarah's `GeneratedScript`**, with two differences: (1) the script persists as **raw text** not `model_dump_json`, so the durable sidecar lift is **13.8** (not automatic); (2) 13.7 also wires feedback into the prompt (Mary's 12.4 already had feedback-regen; Sarah's 13.5 deferred it here).

**`src/ai_qa/agents/bob.py` — the feedback-into-regeneration analog (Story 11.6).** Bob's reprocess feeds reviewer feedback into `RequirementFormatter.convert_page(page, feedback=...)` for a true LLM re-run. 13.7's `ScriptGenerator.generate(..., feedback=...)` is the same idea for scripts. Bob's timestamp pattern (`datetime.now(UTC).isoformat()` [:1177](src/ai_qa/agents/bob.py:1177)) is the one to mirror for `approved_at`.

**`src/ai_qa/pipelines/context.py` — the approving user.** `PipelineContext` ([:11-20](src/ai_qa/pipelines/context.py:11)) carries `user_id: UUID` + `user_email: str` (both always present — the dataclass requires them), plus optional `project_id`/`thread_id`/`agent_run_id`. `approved_by = ctx.user_email or str(ctx.user_id)` (email is the human-readable identity; fall back to the id only if email is somehow empty). Narrow `self.project_context is not None` first (Pyrefly) — `SarahAgent` already raises if it's None on the save path.

**`src/ai_qa/pipelines/script_generator.py` — the generator to extend.** `generate(test_cases, target_url)` ([:64-68](src/ai_qa/pipelines/script_generator.py:64)) loops `_generate_single_script`; neither accepts feedback today. Add `feedback: str | None = None` to both + inject into the prompt builder. Keep the signature backward-compatible (optional, default `None`) so the non-reject generate path is unchanged.

**`frontend/src/components/agents/SarahScriptReviewPanel.tsx` / `App.tsx` — small surface only.** 13.5 built the panel + the `script_review` branch + `handleSarahApprove`/`Reject`; 13.6 threaded `script_content`. 13.7 only adds two optional fields to `ScriptReviewItem` and renders the "Approved by … · …" caption on approved items. No new handler, no new payload type.

### AC1 — approval metadata is recorded on the model, lifted to the artifact by 13.8

AC1 says "approval metadata records user and timestamp." 13.7 records it on the in-memory `GeneratedScript` (`approved_by`/`approved_at`) and surfaces it in the review payload + panel — exactly mirroring 12.4's `TestCase` stamp. Because a **script is saved as raw `.py` text** (not `model_dump_json`), the stamp does **not** auto-persist through `save_script`; its **durable** artifact home is the metadata sidecar, which **13.8** owns (its AC explicitly lists "approval status … creator, updater … timestamp"). This is the precise 12.4→12.5 split re-applied: **13.7 stamps + surfaces; 13.8 lifts into the durable sidecar.** Keep the `GeneratedScript` fields stable + complete so 13.8 only lifts, not re-derives. **CONFIRMED (Q#2): durable persistence stays in 13.8** — do NOT add the two fields to `_write_approved_scripts_metadata` in 13.7 (the rejected alternative); the model stamp + payload surface is the whole of 13.7's AC1 recording.

### AC2 — feedback-into-regeneration (the substance 13.5 deferred here)

13.5 preserved Epic-5's **same-prompt re-run** on reject and wrote, verbatim, that it does **not** "wire feedback into the generation prompt … that is 13.7." 13.7 delivers it: the rejection `feedback` (already threaded `handle_reject(feedback, data)` → `process(feedback=...)` → `_regenerate_current_script(feedback)`) now reaches `ScriptGenerator.generate(..., feedback=...)` and is injected into the prompt so the revised script reflects the correction (mirror Bob 11.6 `convert_page(page, feedback=...)`). "Where possible" is the AC's own hedge: if the generator can't act on it (LLM error, empty feedback), fall back to the existing re-run + error path. The replace-at-index + re-present + clear-approval behavior (13.5 + Task 2) is unchanged.

### AC3 — Jack-eligibility is structural (no Jack code in 13.7)

Jack is **Epic 15** (`backlog`). AC3's "excluded from Jack execution input" is satisfied the way 13.1's "only approved test cases" is satisfied for Mary's output: **structurally**. `save_script` runs **only** in the approve path, so only approved script **content** is persisted as `kind="playwright_script"` under `test_scripts/`; skip never saves; reject regenerates (the old content is replaced) and the new script is unapproved until re-approved. **Story 15.1** (Jack — approved-script input selection, the analog of 13.1's `load_approved_test_cases`) will add `load_approved_scripts` and filter on the `approved` flag/metadata — exactly the third instance of the `12.1 → 13.1 → 15.1` "load approved {X}, thread-prioritize, confirm before {downstream}" pattern. 13.7's job: guarantee the producer never marks/persists an unapproved script as approved, and document the contract. **Do not** pre-build `load_approved_scripts` (CONFIRMED — Q#3) — keep the seam for 15.1.

Note: the misleadingly-named `_write_approved_scripts_metadata` ([sarah.py:738-756](src/ai_qa/agents/sarah.py:738)) currently writes a `kind="configuration"` sidecar for **every** generated script (including unapproved), not just approved ones. This does **not** make unapproved scripts eligible for Jack (Jack queries `kind="playwright_script"`, not `configuration`), so it is **not** an AC3 violation — but it is wrong metadata and is **13.8's** to fix (only write approved + carry approval status). Flag it for 13.8 in Completion Notes; do not fix it here.

### Validation errors vs approval (two distinct gates)

13.6's `validate_script` is a **blocking** gate **before** save/approve (syntax + unsafe-pattern). 13.7's stamp lands **only after** a passing validate + save. So an edited script that fails validation is never stamped (Task 7 asserts this). Keep the two cleanly separated: validation decides *whether* the approve proceeds; the stamp records *who/when* once it does.

### Architecture compliance (hard rules)

- **Mandatory human review at every step — no auto-advance, no bulk approve** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). Approve/reject stay explicit + per-item; the stamp is a record, not a gate change; advancing to Jack is an explicit downstream action (Epic 15). No "Are you sure?" modal ([ux-design-specification.md:1426](_bmad-output/planning-artifacts/ux-design-specification.md:1426)).
- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518,533](_bmad-output/planning-artifacts/architecture.md:518)). 13.7 adds **no** storage access; the approved script saves through the **existing** `save_script` ([artifact_adapter.py:143](src/ai_qa/pipelines/artifact_adapter.py:143)).
- **No credential/secret leakage** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md), [architecture.md:362-373](_bmad-output/planning-artifacts/architecture.md:362)): the `approved_by` is a user email/id (already known to the client) — fine to surface. The reject `feedback` injected into the prompt must **not** be logged alongside the raw script body, tokens, or config; the regeneration prompt itself never includes secrets (13.4's secret-scrubbing on the script body is upstream). The review payload carries only `approved_by`/`approved_at` (no new sensitive field).
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the new `ScriptReviewItem.approved_by`/`approved_at` ↔ the payload keys ↔ the `GeneratedScript` fields must match exactly; verify with `npm run typecheck`/`build`.
- **Sarah flow** `script_generator.py → ai_connection + browser/agent.py → projects/{project_id}/test_scripts/` ([architecture.md:824-828](_bmad-output/planning-artifacts/architecture.md:824)) — unchanged; 13.7 only stamps the model + threads feedback into the prompt.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Pyrefly-clean: narrow `self.project_context` (`… | None`) and `data.get("script_index")` (`Any | None`) before use; `approved_by`/`approved_at` are `str | None`; do **not** `str()` a value already typed `str` (Pyrefly `unnecessary-type-conversion`) — `ctx.user_email or str(ctx.user_id)` only `str()`s the `UUID`; no redundant casts; `from datetime import UTC, datetime`. No bare `except Exception` where a specific type fits. `pytest.raises` needs a specific type + `match=`. The agent path uses a **sync** artifact `Session`.
- **Frontend:** React 19.2, TS ~6.0 strict (`npm run typecheck`), Tailwind v4, Vitest 4 (`vi.mock` hoisted file-wide — mock `SyntaxHighlighter`/`ScrollArea`; prefer `vi.spyOn(globalThis,"fetch")`; preserve real exports via `importOriginal()`), ESLint 9. Path alias `@` → `./src`. Strict null/index access — non-null assert known array elements (`scripts[i]!`). Status/approval caption use color **+ text**, never color alone. No new packages. Playwright: `getByRole`/`getByText`; no `page.route`, no `waitForTimeout`.

### Project Structure Notes

- **New files:** none required (extends existing). New test fixtures only if needed.
- **Modified files (expected):** `src/ai_qa/agents/sarah.py` (`GeneratedScript` fields; stamp in `handle_approve`; clear in `handle_reject`; `feedback` through `_regenerate_current_script`; two payload keys in `_present_script_review`; AC3 contract comment), `src/ai_qa/pipelines/script_generator.py` (`generate`/`_generate_single_script` optional `feedback` + prompt injection), `frontend/src/types/testcase.ts` or `script.ts` (`ScriptReviewItem.approved_by`/`approved_at`), `frontend/src/components/agents/SarahScriptReviewPanel.tsx` (approval caption), `tests/test_agents/test_sarah.py`, `tests/pipelines/test_script_generator.py`, `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx`, possibly `frontend/e2e/epic-13.spec.ts`.
- **No backend route/schema/REST changes, no new WS router action** — approval rides the existing `data` channel + `script_review` payload. **No Alembic migration** (in-memory Pydantic model; raw-text artifact).

### Testing standards summary

- Backend: pytest; Sarah approval/reject/feedback tested by seeding `_generated_scripts` + `agent.phase="script_review"` and patching `ai_qa.agents.sarah.PipelineArtifactAdapter`/`ScriptGenerator` ([test_sarah.py:172-212](tests/test_agents/test_sarah.py:172)); assert the **stamp** on approve, the **cleared** stamp on reject, the **feedback** in `ScriptGenerator.generate`'s call args, and that skip/reject never persist an approved script. `ScriptGenerator` feedback-injection tested in `tests/pipelines/test_script_generator.py`. Whole suite `--no-cov`; mypy `src`.
- Frontend: Vitest on the panel (approval caption present/absent/null-safe); mirror `SplitPanel.test.tsx` scaffolding. Playwright scoped per Task 8.

### Previous-story / sibling intelligence

- **Story 12.4 (Mary review workflow)** — the **direct analog**: `approved_by`/`approved_at` stamp on the model, cleared on regenerate, durable lift deferred to 12.5; index-addressable approve/reject keyed off `_reviewed_indices`. 13.7 re-applies all of it to `GeneratedScript`, plus the feedback-into-prompt that Mary already had.
- **Story 13.5 (Sarah side-by-side review UX)** — built the panel + present-all transport + index-addressable handlers + `_reviewed_indices`, and **explicitly deferred to 13.7**: approval `user`/`timestamp` metadata, feedback-into-the-generation-prompt, "rejected output never treated as approved" (beyond clearing `approved`), and the Jack-eligibility filter. 13.7 supplies exactly those (the Jack filter as a structural contract for 15.1, not Jack code).
- **Story 13.6 (script edit before approval)** — added the edit pane + `validate_script` gate inside the same `handle_approve` branch; fenced approval metadata + reject/regenerate semantics + Jack-eligibility to 13.7. 13.7's stamp lands after 13.6's validate+save and is independent of the edit.
- **Story 13.8 (test script artifact save)** — the explicit downstream fence: lifts `approved_by`/`approved_at` + source test case artifact ID + approval status + validation status into the durable artifact-save metadata/sidecar, adds save idempotency/D8, and fixes the `.spec.ts` fallback + the `_write_approved_scripts_metadata`-writes-all-scripts bug. 13.7 must not pre-empt it.
- **Story 15.1 (Jack — approved-script input selection)** — the consumer of AC3: `load_approved_scripts` (analog of 13.1's `load_approved_test_cases`) filters on the `approved` flag/metadata 13.7 guarantees. Keep the producer-side contract clean + documented so 15.1 just reads it.
- **Story 11.6 (Bob reviewable extraction output)** — the feedback-into-regeneration precedent (`convert_page(page, feedback=...)`) + the `datetime.now(UTC).isoformat()` timestamp pattern.
- **Epic 5 (Sarah, done)** — built `GeneratedScript`, the per-item review loop, `save_script`, `_regenerate_current_script`, `_write_approved_scripts_metadata`. 13.7 extends the model + the reject regeneration; it changes neither the save call nor the metadata sidecar.

### Git intelligence (recent work patterns)

Recent commits (`79f3f3c epic 11 can read confluence page`, `2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`) are Epic 10/11. **Epic 12 (12.1–12.5) and Stories 13.1–13.6 are NOT implemented** — the live `sarah.py`/`App.tsx`/`GeneratedScript`/`ScriptGenerator` are pre-13.x (verified at `79f3f3c`: `handle_approve` ignores `data` + saves the original, no phase-dispatch, no `_reviewed_indices`, no `script_review`, no `SarahScriptReviewPanel`; `_regenerate_current_script` drops feedback; `GeneratedScript` has no `approved_by`/`approved_at`/`warnings`). **13.7 is blocked until 13.1–13.6 land** — verify in the live tree (Task 0) and flag/stop if unmerged rather than re-implementing upstream. Closest existing patterns to copy: [12-4-mary-review-workflow.md](_bmad-output/implementation-artifacts/12-4-mary-review-workflow.md) (the approve/reject/regenerate + stamp analog), [bob.py:1130-1207](src/ai_qa/agents/bob.py:1130) (feedback-into-regeneration + timestamp), [alice.py:25,996](src/ai_qa/agents/alice.py:25) (`datetime.now(UTC).isoformat()`), and the **13.5/13.6 stories** (the handlers + panel + transport this story refines).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-13.7] — ACs (lines 1389-1409); Epic 13 intro + FRs incl. **FR20 approve/reject generated scripts** (1253-1257); siblings 13.5 review UX (1345-1365), 13.6 edit (1367-1387), 13.8 save (1411-1430); Jack/Epic 15 input selection (15.1)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR20 "Reviewer can approve or reject generated scripts" (381); FR19 side-by-side review (380); generated-script spec — Python/Playwright/assertions/stable selectors (309-316); security/no-secrets-in-scripts (237-243, 465-475)
- [Source: _bmad-output/planning-artifacts/architecture.md] — mandatory review / no auto-advance (271-272); no-direct-storage (518, 533); Sarah flow → test_scripts/ (824-828); security/read-only/no-secret-leakage (362-373)
- [Source: src/ai_qa/agents/sarah.py] — `GeneratedScript` (26-37); `handle_approve` accepts-but-ignores `data`, saves original (519-570, save 537-540); `handle_reject` (572-619); `_regenerate_current_script` drops feedback (373-454, 412-414); `handle_skip` (621-666); `_present_current_script_for_review`/`review_data` (698-736); `_write_approved_scripts_metadata` writes-all-scripts (738-756) = 13.8; `.spec.ts` fallback = 13.8 (538)
- [Source: src/ai_qa/agents/mary.py + 12-4 story] — the `approved_by`/`approved_at` stamp + clear-on-regenerate analog; 12.4↔12.5 boundary
- [Source: src/ai_qa/agents/bob.py] — feedback-into-regeneration (`convert_page(page, feedback=...)`, 11.6); `datetime.now(UTC).isoformat()` (2, 1177)
- [Source: src/ai_qa/agents/alice.py] — `from datetime import UTC, datetime` (25), `datetime.now(UTC).isoformat()` (996)
- [Source: src/ai_qa/pipelines/context.py] — `PipelineContext.user_email`/`user_id` for the approval stamp (11-20)
- [Source: src/ai_qa/pipelines/script_generator.py] — `generate(test_cases, target_url)` to extend with `feedback` (64-68); `_generate_single_script` + prompt builders; `_calculate_confidence` (494) = untouched
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `save_script` (143-145, runs only on approve = AC3 structural basis); `_save_text`/`save_metadata` (151-202); `load_scripts` (147-149) — the surface 15.1's `load_approved_scripts` mirrors
- [Source: src/ai_qa/artifacts/storage.py] — `playwright_script`/`testscript` → `test_scripts/` (28-38, 34-35)
- [Source: src/ai_qa/api/websocket.py] — dispatch `approve`→`handle_approve(data)` / `reject`→`handle_reject(feedback, data)` with full `data` passthrough (312-322) — no change needed
- [Source: tests/test_agents/test_sarah.py] — Sarah test scaffold (patch adapter+ScriptGenerator 172-212; approve/reject/skip/navigate tests 411-800)
- [Source: tests/pipelines/test_script_generator.py] — script-generator test scaffold (extend for feedback injection)
- [Source: frontend/src/components/__tests__/SplitPanel.test.tsx] — review-panel Vitest scaffold to mirror
- [Source: _bmad-output/implementation-artifacts/13-5-sarah-side-by-side-review-ux.md] — the panel + transport + index-addressable handlers + the explicit "13.7" deferral list
- [Source: _bmad-output/implementation-artifacts/13-6-script-edit-before-approval.md] — the edit+validate gate 13.7's stamp lands after
- [Source: _bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md] — the phase-dispatch + the `12.1→13.1→15.1` "load approved" pattern AC3 hands to 15.1
- [Source: _bmad-output/implementation-artifacts/12-4-mary-review-workflow.md] — the direct analog (stamp + clear + index-addressable; 12.4↔12.5 boundary = 13.7↔13.8)
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional/Any, no redundant cast/conversion); no bare except; no `# type: ignore`; full-stack sync; no new packages; security (no secrets in payloads/logs)

## Confirmed decisions (defaults locked by Thuong 2026-06-13 — "áp dụng default")

All four formerly-open questions are resolved to their defaults. No pending input — implement exactly as stated.

1. **AC2 — feedback IS wired into the regeneration prompt (CONFIRMED — Q#1).** Extend `ScriptGenerator.generate(..., feedback=...)` + `_generate_single_script` to inject the reviewer's rejection feedback into the prompt (mirror Bob 11.6 `convert_page(page, feedback=...)` / Mary 12.4), so the regenerated script reflects the correction; "where possible" = fall back to the existing same-prompt re-run + error path only when the generator/LLM errors or the feedback is empty. (Rejected: keep the same-prompt re-run and acknowledge feedback **only** in the chat message with no `ScriptGenerator` change — minimal, but then AC2's "revise where possible" degrades to "regenerate (same prompt)".)
2. **AC1 — durable persistence of `approved_by`/`approved_at` stays in 13.8 (CONFIRMED — Q#2).** 13.7 stamps the `GeneratedScript` model + surfaces the two fields in the `script_review` payload + the panel (the whole of 13.7's AC1 recording); **13.8** lifts them (plus source test case artifact ID + approval status + validation status) into the durable artifact-save sidecar/metadata. Strict 12.4→12.5 mirror. (Rejected: 13.7 also adding the two fields to the existing `_write_approved_scripts_metadata` sidecar now — would blur the 13.7/13.8 boundary; the script-as-raw-text reality makes the sidecar 13.8's to own anyway.)
3. **AC3 — do NOT pre-build the `load_approved_scripts` (Jack) seam (CONFIRMED — Q#3).** AC3 is a producer-side structural guarantee (only approved script content reaches `test_scripts/`; reject/skip/regenerate never mark approved) + a documented contract. **Story 15.1** adds `load_approved_scripts` (the `12.1→13.1→15.1` pattern). 13.7 writes no Jack code and no loader. (Rejected: adding a read-only `load_approved_scripts` loader now — harmless but untested-in-context until Epic 15, and it would invite scope creep into Jack's input-selection.)
4. **E2E coverage = scoped (CONFIRMED — Q#4).** Backend pytest (stamp-on-approve, clear-on-reject, feedback-into-`generate`, structural eligibility) + Vitest (panel approval caption) are the primary guardrails. Playwright E2E reaches the approval-caption surface only when a Chrome path + provider key are present, else deferred to Vitest — LLM-driven generation isn't E2E-reproducible without a provider key and `page.route` mocking is forbidden; the chrome-path FE is deferred (13.1). (Rejected: full LLM-driven E2E — same reasons 13.5/13.6 rejected it.)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

No debug issues encountered.

### Completion Notes List

- **Task 0 — Prerequisites verified:** 13.1 (phase-dispatch, `self.phase`, `confirmed_test_cases`), 13.5 (`SarahScriptReviewPanel`, `_reviewed_indices`, present-all transport), 13.6 (`validate_script`, Edit tab) all merged and confirmed live. Divergences from story's line-number citations were expected (stories 13.1–13.6 changed the file significantly from baseline `79f3f3c`); all code was reconciled against the live tree before relying on it.
- **Task 1 — AC1 approval stamp:** Added `approved_by: str | None` + `approved_at: str | None` to `GeneratedScript`. `from datetime import UTC, datetime` added to imports. Stamp placed AFTER 13.6's validate+save in `handle_approve`'s script-review branch. Not stamped on validation-failure early-return. `_write_approved_scripts_metadata` left unchanged per 13.7↔13.8 boundary (durable sidecar lift = 13.8).
- **Task 2 — AC2/AC3 reject-clear:** In `handle_reject`, cleared `approved_by = None` and `approved_at = None` on the rejected script index before regeneration. The replacement `GeneratedScript(...)` in `_regenerate_current_script` is a fresh object (default `None`s) — confirmed no stale carry-over.
- **Task 3 — AC2 feedback-into-regeneration:** Extended `ScriptGenerator.generate`, `_generate_single_script`, `_call_llm`, and `_call_llm_with_vision` with optional `feedback: str | None = None`. Feedback injected as a `"---\nReviewer feedback to address in this revision:\n{feedback}\n---"` block appended to the prompt. Sanitized to 2000 chars; empty/whitespace feedback skipped (same-prompt path unchanged). Removed stale `# Note: feedback is not yet supported` comment. `_regenerate_current_script` now passes `feedback=feedback` to `generate`.
- **Task 4 — AC1 payload:** Added `"approved_by": s.approved_by` and `"approved_at": s.approved_at` to each entry in `_present_script_review`. Rides the existing `script_review` payload (no new message type, no router change).
- **Task 5 — AC3 structural contract:** Added contract comment at `save_script` call site in `handle_approve` documenting the Jack-eligibility guarantee for Story 15.1. Verified `_handle_skip_script` does NOT call `save_script` and does NOT set `approved` — structural exclusion is correct. `load_approved_scripts` left to 15.1. Note: `_write_approved_scripts_metadata` currently writes a `kind="configuration"` sidecar for ALL scripts (not just approved) — this is not an AC3 violation (Jack queries `kind="playwright_script"`, not `configuration`) but is technically wrong and flagged for 13.8 to fix.
- **Task 6 — Frontend full-stack sync:** Extended `ScriptReviewItem` in `testcase.ts` with `approved_by?: string | null` and `approved_at?: string | null`. Added `ApprovalCaption` helper component and `formatApprovedAt` function to `SarahScriptReviewPanel.tsx`. Caption renders "Approved by {user} · {formatted timestamp}" using green text + `UserCheck` icon (color + text, not color alone). Null-safe for both fields. Confirmed `handleSarahReject` already threads feedback via 13.5's WS message — no change needed.
- **No Alembic migration needed:** `GeneratedScript` is an in-memory Pydantic model, not a DB table. Scripts persist as raw `.py` text via `save_script`. Approval metadata persistence is 13.8's (durable sidecar).
- **Deferred to 13.8:** `approved_by`/`approved_at` lift into `_write_approved_scripts_metadata` sidecar + source test case artifact ID + approval status + validation status + D8 idempotency + `.spec.ts` fallback fix.

### File List

- `src/ai_qa/agents/sarah.py`
- `src/ai_qa/pipelines/script_generator.py`
- `frontend/src/types/testcase.ts`
- `frontend/src/components/agents/SarahScriptReviewPanel.tsx`
- `tests/test_agents/test_sarah.py`
- `tests/pipelines/test_script_generator.py`
- `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx`
- `_bmad-output/implementation-artifacts/13-7-script-approval-rejection-and-regeneration.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-06-17: Implemented Story 13.7 — script approval/rejection/regeneration semantics layer for Sarah. Added `approved_by`/`approved_at` to `GeneratedScript`, stamped on approve, cleared on reject; wired reviewer feedback into `ScriptGenerator.generate` prompt; surfaced approval metadata in the `script_review` payload + `ScriptReviewItem` TS type + panel caption. Backend: 1373 passed (no regression). Frontend: 263 passed (no regression). mypy clean, ESLint clean, typecheck clean.
