---
baseline_commit: 79f3f3c
---

# Story 13.8: Test Script Artifact Save

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want approved Playwright scripts saved as project artifacts under `projects/{project_id}/test_scripts/` with complete, real provenance metadata (one per source test case), and made reachable through project-scoped approved-only artifact queries,
so that Jack and other project members can run or inspect them later without ever consuming an unapproved, mislabeled, or partial script set.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.8](_bmad-output/planning-artifacts/epics.md) (lines 1411-1430), expanded with implementation defaults (see "Scope decisions" — confirm or correct via Saved Questions). This is the **artifact-save** story for Sarah — the script analog of **Story 12.5** (Mary's test-case save), which is itself the test-case analog of **Story 11.7** (Bob's requirements save). It makes the on-approve script save **authoritative, fully-provenanced, idempotent, and approved-only**, and fixes three live defects in the save path.

### AC1 — Approved script is saved under `projects/{project_id}/test_scripts/`, one per source test case

- **Given** a script is approved
- **When** Sarah saves it
- **Then** the artifact service stores it under `projects/{project_id}/test_scripts/` (the `kind="playwright_script"` → `test_scripts/` storage mapping already exists — [storage.py:34-35](src/ai_qa/artifacts/storage.py:34))
- **And** **one approved script artifact is saved per source test case** — a re-approval (after reject/regenerate or a retried approve) of the same test case converges to **exactly one** artifact, not a duplicate (requires idempotent-by-name `save_script`; the save filename is the script's `.py` name — fix the `.spec.ts` fallback at [sarah.py:538](src/ai_qa/agents/sarah.py:538))

### AC2 — Script artifact metadata includes full provenance

- **Given** script artifact metadata is saved
- **When** it is inspected
- **Then** it includes **source test case artifact ID**, **output path or logical path**, **approval status** (`approved_by` + `approved_at`), **creator**, **updater**, **originating thread**, **originating agent run**, **validation status**, and **timestamp**.
- The native `Artifact` columns already record **creator** (`created_by_user_id`), **updater** (`updated_by_user_id`), **originating thread** (`thread_id`), **originating agent run** (`agent_run_id`), and **timestamp** (`created_at`/`updated_at`) — set by `save_script` → `save_artifact`. The **script-specific** fields (source test case artifact ID, output/logical path, approval status, validation status, model, confidence) are durably persisted in the **metadata side-car** (`{filename}.metadata.json`, `kind="configuration"`), because — unlike a `TestCase` (saved as `model_dump_json`) — a **script is saved as raw `.py` text** ([artifact_adapter.py:143-145](src/ai_qa/pipelines/artifact_adapter.py:143)), so its provenance has no JSON-content home. The current side-car ([sarah.py:738-756](src/ai_qa/agents/sarah.py:738)) is **fake/thin** (`source_url: script.test_case.filename`, hardcoded `model`/`confidence`, written for **every** generated script including skipped/failed) — this story makes it **real and approved-only**.

### AC3 — Saved scripts are reachable through project-scoped approved-only artifact queries (no workspace paths)

- **Given** Jack requests executable scripts for the selected project
- **When** approved script artifacts exist
- **Then** only **project-scoped approved** script artifacts are returned through artifact service queries (`ArtifactService.list_artifacts(project_id, kind="playwright_script")` / `PipelineArtifactAdapter.load_scripts()`), with **no** workspace-path read.
- **"Only approved" is structural, not filtered** — `save_script` runs **only** in the approve path (skip/reject/regenerate never persist a script), so every `kind="playwright_script"` artifact is approved by construction. Jack's actual input-selection loader (`load_approved_scripts`) is **Story 15.1**, not this story (the `12.1 → 13.1 → 15.1` "load approved {X}" pattern). 13.8 owns the producer-side guarantee + proves the query surface with a test.

---

## ⚠️ CRITICAL: This is the script analog of Story 12.5 — it makes the script save AUTHORITATIVE, REAL-METADATA, IDEMPOTENT, and APPROVED-ONLY

By the time control reaches this story, Sarah already saves approved scripts: after **13.1–13.7** merge, the per-item review loop approves each script and `save_script` persists the (possibly edited) content as `kind="playwright_script"` under `test_scripts/`, and at `DONE` `SarahAgent._write_approved_scripts_metadata` writes a side-car per script. **But that save has three defects this story fixes:**

1. **The side-car metadata is fake AND written for every script.** [`_write_approved_scripts_metadata`](src/ai_qa/agents/sarah.py:738) iterates **all** `self._generated_scripts` (including **skipped**, **failed-placeholder**, and **unapproved** ones — [sarah.py:744](src/ai_qa/agents/sarah.py:744)) and writes `{"source_url": script.test_case.filename, "model": ..., "confidence": ..., "test_case_title": ...}` — `source_url` is a **filename, not a URL**, and it omits the **source test case artifact ID**, **approval status** (`approved_by`/`approved_at`, added by 13.7), **validation status** (13.6), and **output/logical path**. This is the script analog of 12.5's fake-`confidence:1.0` side-car, but worse (it leaks unapproved scripts into the metadata folder).
2. **The save filename fallback names a Python script `.spec.ts`.** [sarah.py:538](src/ai_qa/agents/sarah.py:538): `Path(current_script.file_path).name or f"{current_script.test_case.filename}.spec.ts"`. Sarah generates **Python** Playwright scripts (`_generate_filename` → `test_*.py` — [script_generator.py:436-466](src/ai_qa/pipelines/script_generator.py:436)), so the TypeScript `.spec.ts` fallback is wrong. Fix to `.py`.
3. **`save_script` is not idempotent-by-name.** Unlike `save_requirement` (D8, 11.8) and `save_test_case` (12.5), [`save_script`](src/ai_qa/pipelines/artifact_adapter.py:143) always creates a **new** row, so a reject→regenerate→re-approve (or a retried approve) of the same test case **duplicates** the script artifact, violating AC1's "one approved script artifact per source test case".

Story 13.8 does exactly four things and **nothing else**:

1. **Populate real save metadata, approved-only (AC1 + AC2).** Rewrite `_write_approved_scripts_metadata` to iterate **only approved** scripts and lift the **real** values from each `GeneratedScript`: **source test case artifact ID** (the `Artifact.id` of the test case the script was generated from — see "The source-test-case-artifact-ID gap"), **output/logical path** (`file_path` + the saved artifact's `storage_path`), **approval status** (`approved_by`/`approved_at`, 13.7), **validation status** (13.6), `model`, `confidence`, `test_case_title`. The native columns cover creator/updater/thread/agent-run/timestamp.
2. **Fix the `.spec.ts` → `.py` fallback (AC1).** At the `save_script` call site in `handle_approve` ([sarah.py:537-540](src/ai_qa/agents/sarah.py:537)), the no-`file_path` fallback must be `f"{current_script.test_case.filename}.py"` (Python), not `.spec.ts`.
3. **Make `save_script` idempotent-by-name (AC1).** Mirror `save_requirement`'s D8 pattern (snapshot prior `kind="playwright_script"` rows with the same name → save the new copy first → delete the superseded rows after) so a re-approval converges to exactly one artifact per script name instead of duplicating.
4. **Confirm + prove the project-scoped approved-only query surface (AC3).** `kind="playwright_script"` already maps to `test_scripts/` and is listable via `ArtifactService.list_artifacts(kind="playwright_script")` / `PipelineArtifactAdapter.load_scripts()` with **no** workspace path. Prove it with a test; Jack's `load_approved_scripts` loader is **Story 15.1**, not this story.

### Confirmed scope decisions (defaults — Thuong confirms or corrects via Saved Questions)

- **No new DB columns / no Alembic migration.** `kind="playwright_script"` → `test_scripts/` mapping already exists ([storage.py:34-35](src/ai_qa/artifacts/storage.py:34)); the 11.7 provenance columns (`source_type`/`source_url`/`warnings`) already exist (migration `c8e6ace95b08`); `GeneratedScript` is an in-memory Pydantic model (not a DB table); the script persists as raw `.py` text. **State this explicitly in Completion Notes** (mirrors 12.5).
- **Metadata carrier = the expanded side-car + the native columns.** Because the script is raw text (no `model_dump_json` content carrier), the **side-car** is the authoritative durable record of the script-specific provenance, and the native columns cover creator/updater/thread/agent-run/timestamp. (This is the one real difference from 12.5, where the test-case JSON content **also** durably carries source/confidence/approval.)
- **"Only approved" is structural (no discriminator column).** `save_script` runs only on approve, so every `playwright_script` artifact is approved by construction — exactly like test cases (no draft script exists). AC3's "only approved" needs **no** filter/discriminator (note this for 15.1).
- **Idempotent-by-name save** so a reject→regenerate→re-approve converges to exactly one script artifact per name (no duplicates).

### In scope

- **Agent:** `SarahAgent._write_approved_scripts_metadata` rewritten — **approved-only** iteration + **real** metadata (source test case artifact ID, output/logical path, approval status, validation status, model, confidence, title), stale-`source_url`-as-filename cleanup. The `save_script` call site fallback fixed to `.py`.
- **Adapter:** `PipelineArtifactAdapter.save_script(...)` made **idempotent-by-name** (mirror `save_requirement`/`save_test_case`).
- **`GeneratedScript`:** carries the **source test case artifact ID** so AC2 can lift it (see "The source-test-case-artifact-ID gap" — reconcile with 13.1; add the field minimally if 13.1/13.2 did not).
- **Tests:** real side-car metadata round-trip (AC2), approved-only side-car (AC1 — skipped/failed/unapproved excluded), `.py` fallback name (AC1), idempotent-retry convergence (AC1), AC3 query reachability via `load_scripts()` (no workspace path, project-scoped), plus regression on the existing approve/skip/metadata tests.

### Out of scope (do NOT build)

- **No Jack / Epic 15 consumption logic.** AC3's "Jack requests approved scripts" is satisfied by **query reachability** (scripts listable/readable by project + `kind="playwright_script"`, no workspace path). The actual input-selection loader (`load_approved_scripts` — the analog of 13.1's `load_approved_test_cases`), thread-prioritization, and Jack's confirm UI are **Story 15.1**. Do not build Jack's loader here — just prove the query surface returns approved scripts.
- **No generation / selector / SSO / confidence / review-UI / edit-validate / approve-reject-semantics changes.** Generation = 13.2, selectors/assertions = 13.3, SSO = 13.4, the review panel + present-all transport + index-addressable handlers = 13.5, edit + `validate_script` = 13.6, approve/reject/regenerate + `approved_by`/`approved_at` stamping + feedback-into-prompt = 13.7. 13.8 only changes how the **already-approved** script set is **persisted, named, made-real-in-metadata, deduped, and queried**.
- **No new frontend component and no TS interface change.** 13.8 is backend-only; the `ScriptReviewItem` TS interface (incl. `approved_by`/`approved_at`) was synced by 13.5/13.7. Run `npm run typecheck` only to confirm nothing broke.
- **No change to `save_artifact`'s atomic write, `create_version`, the WebSocket router, secret resolution, or the MCP/LLM paths.** The save path opens no MCP client and calls no LLM.
- **No new "approved" discriminator column for scripts** — every saved `playwright_script` artifact is approved by construction (note for 15.1).

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action for 13.8 |
| --- | --- | --- |
| `kind="playwright_script"` → storage key `projects/{project_id}/test_scripts/{artifact_id}/v{version}/{name}` | [storage.py:34-35](src/ai_qa/artifacts/storage.py:34) | ✅ done — **AC1 path is already correct; no storage change** |
| `kind in ("testscript","playwright_script")` → browse folder `test_scripts` | [storage.py:57-58](src/ai_qa/artifacts/storage.py:57) | ✅ done — tree/UI folder grouping already correct |
| `SarahAgent._write_approved_scripts_metadata` (writes a side-car for **every** script with fake `source_url`/hardcoded fields) | [sarah.py:738-756](src/ai_qa/agents/sarah.py:738) | ⚠️ **rewrite** — approved-only + real metadata (AC1, AC2); remove `source_url: filename` |
| `SarahAgent.handle_approve` `save_script(...)` call with `.spec.ts` fallback | [sarah.py:537-540](src/ai_qa/agents/sarah.py:537) (13.7 reshapes this branch to index-addressable + stamp) | ⚠️ **fix fallback** `.spec.ts` → `.py` (AC1); do **not** re-do 13.7's stamp |
| `PipelineArtifactAdapter.save_script(name, script_content)` → `_save_text(kind="playwright_script")` | [artifact_adapter.py:143-145](src/ai_qa/pipelines/artifact_adapter.py:143) | ⚠️ **make idempotent-by-name** (mirror `save_requirement`/`save_test_case`) |
| `PipelineArtifactAdapter.save_requirement` — idempotent-by-name reference (snapshot prior → save new first → delete superseded) | [artifact_adapter.py:51-103](src/ai_qa/pipelines/artifact_adapter.py:51) | ✅ done — **copy this D8 pattern into `save_script`** |
| `PipelineArtifactAdapter.save_test_case` made idempotent in 12.5 (same D8 pattern, the **closest** mirror) | 12.5's [artifact_adapter.py:134-137](src/ai_qa/pipelines/artifact_adapter.py:134) | ✅ (after 12.5) — **the exact shape to copy for `save_script`** |
| `PipelineArtifactAdapter.load_scripts()` → `_load_text_artifacts(kind="playwright_script")` (project-scoped, no workspace path) | [artifact_adapter.py:147-149,245-247](src/ai_qa/pipelines/artifact_adapter.py:147) | ✅ done — **AC3 query seam; prove with a test** (15.1 consumes it) |
| `PipelineArtifactAdapter.save_metadata(name, dict)` → `kind="configuration"` JSON side-car | [artifact_adapter.py:151-157](src/ai_qa/pipelines/artifact_adapter.py:151) | ✅ done — **reuse for the expanded real side-car** |
| `ArtifactService.save_artifact(...)` — atomic write (DB rollback + storage delete on exception) | [service.py:74-140](src/ai_qa/artifacts/service.py:74) | ✅ done — **no change; per-artifact atomicity underpins the idempotent save ordering** |
| `ArtifactService.delete_artifact(*, project_id, artifact_id) -> bool` | [service.py:211-234](src/ai_qa/artifacts/service.py:211) | ✅ done — **reuse for the idempotent dedupe in `save_script`** |
| `ArtifactService.list_artifacts(*, project_id, kind)` (project-scoped) + `read_current_content` | [service.py:194-201,236-238](src/ai_qa/artifacts/service.py:194) | ✅ done — **AC3 query surface** |
| Native `Artifact` columns: `created_by_user_id`/`updated_by_user_id`/`thread_id`/`agent_run_id`/`created_at`/`updated_at` | set by `save_artifact` from `PipelineContext` | ✅ done — **cover AC2's creator/updater/thread/agent-run/timestamp** |
| `GeneratedScript` model (`test_case`/`script_content`/`file_path`/`confidence`/`approved`/`error_message`; **+ `warnings`** from 13.2, **+ `approved_by`/`approved_at`** from 13.7) | [sarah.py:26-37](src/ai_qa/agents/sarah.py:26) + 13.2/13.7 | ⚠️ **read** `approved_by`/`approved_at`; **possibly EXTEND** with `source_test_case_id` + validation status if 13.1/13.6 did not (see below) |
| `TestCase.filename` property (kebab-case) | [models.py:291-298](src/ai_qa/models.py:291) | ✅ reuse — side-car filename + `.py` fallback base |
| `_format_error_message(errors)` — UX-DR12 three-part error (if a recovery message is added) | [base.py](src/ai_qa/agents/base.py) | ✅ done — reuse if Saved Q#3 = YES |
| Story 12.5 (the direct analog) + 11.7 (the original) | [12-5-test-case-artifact-save.md](_bmad-output/implementation-artifacts/12-5-test-case-artifact-save.md), [11-7-requirements-artifact-save.md](_bmad-output/implementation-artifacts/11-7-requirements-artifact-save.md) | ✅ **mirror exactly** — idempotent save, real side-car, query reachability |

---

## ⚠️ Sequencing dependency (READ FIRST — critical)

**Story 13.8 is the LAST story in the `13.1 → 13.2 → 13.3 → 13.4 → 13.5 → 13.6 → 13.7 → 13.8` chain. Stories 13.1–13.7 are `ready-for-dev`, NOT `done`, and Epic 12 (12.1–12.5) is likewise unmerged.** As of this writing the working tree holds the **pre-13.x Epic-5 Sarah** (verified against live code on `79f3f3c`):

- `src/ai_qa/agents/sarah.py` — positional `_current_review_index` lifecycle (no `self.phase`, no `_reviewed_indices`, no `script_review` present-all transport, no `SarahScriptReviewPanel`); `handle_approve` ([sarah.py:519-570](src/ai_qa/agents/sarah.py:519)) accepts-but-ignores `data`, marks `approved=True`, saves the **original** content with the **`.spec.ts`** fallback ([sarah.py:537-540](src/ai_qa/agents/sarah.py:537)), advances linearly, DONE at `>= len`; `_write_approved_scripts_metadata` ([sarah.py:738-756](src/ai_qa/agents/sarah.py:738)) writes a fake side-car for **all** scripts; `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) has **no** `approved_by`/`approved_at`/`warnings`.
- `src/ai_qa/pipelines/artifact_adapter.py` — `save_script` ([:143-145](src/ai_qa/pipelines/artifact_adapter.py:143)) always creates a new row (not idempotent); `save_test_case` ([:134-137](src/ai_qa/pipelines/artifact_adapter.py:134)) is **also** still non-idempotent (12.5 unmerged).

13.8 reads/extends fields and a save path that **only exist after the chain lands**. Specifically 13.8 assumes:

1. **From 13.7:** `GeneratedScript.approved_by` / `approved_at` (the approval stamp this story lifts into the side-car), and 13.7's index-addressable, phase-dispatched `handle_approve` whose `save_script` call this story re-points to a `.py` fallback. 13.8 reads the stamp; it does **not** re-implement it.
2. **From 13.6:** the `validate_script` gate + whatever it records (`script_validation_error` or a validation-passed marker) — 13.8 lifts the **validation status** into the side-car. Reconcile the exact field name against 13.6's implementation.
3. **From 13.2:** `GeneratedScript.warnings` + the generation that links each script to its source test case. 13.8 does **not** change generation; it reads what's there.
4. **From 13.1:** the approved-test-case loader (`load_approved_test_cases`) — **and whether it captures the source test case artifact ID** onto each loaded test case / `GeneratedScript` (see "The source-test-case-artifact-ID gap" — this is the one field with no clear upstream owner).
5. **From 12.5:** the idempotent-by-name `save_test_case` (the exact D8 shape to copy into `save_script`).

**If 13.1–13.7 (and the 12.5 `save_test_case` idempotency) are not all merged when you start, STOP and flag it** — do not re-implement them here, and do not lift fields that don't exist. 13.8 **extends** the 13.x versions of `_write_approved_scripts_metadata` / the `save_script` call site, makes `save_script` idempotent, and reads the 13.6/13.7 fields; it does not re-create the panel, transport, handlers, edit/validate gate, or approval semantics. Reconcile against live code and treat any cited `file:line` / snippet as a **lead to verify**, not gospel — record divergences in Completion Notes (per [verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md) and [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## Tasks / Subtasks

- [x] **Task 0 — Confirm prerequisites (BLOCKING gate)**
  - [x] Verify **13.7** merged: `GeneratedScript.approved_by`/`approved_at` exist and are stamped in `handle_approve`'s script-review branch; `handle_approve` is phase-dispatched + index-addressable. If absent → **flag and stop.**
  - [x] Verify **13.6** merged: `validate_script` + its recorded validation status (`script_validation_error` or equivalent) exist. Record the exact field/shape 13.8 will lift as "validation status". If absent → **flag and stop.**
  - [x] Verify **13.5** merged: `_write_approved_scripts_metadata` is still called on DONE (the present-all/index-addressable refactor may have moved the call site — find where it runs and confirm it runs once when review completes). Record where.
  - [x] Verify **13.1** merged and **inspect whether the approved-test-case load captures the source test case artifact ID** (e.g. a `source_test_case_id` on `GeneratedScript`/`TestCase`, or a parallel id list). Record the answer — it decides whether Task 4 lifts an existing field or adds one (see "The source-test-case-artifact-ID gap").
  - [x] Verify **12.5** merged: `save_test_case` is idempotent-by-name (the D8 shape Task 1 copies). If 12.5 is unmerged but `save_requirement` is, copy the `save_requirement` pattern instead. Record which reference you used.
  - [x] Record all verifications + any divergence (field names, the exact 13.x `handle_approve` branch shape, where `_write_approved_scripts_metadata` runs) in Completion Notes **before** relying on them.

- [x] **Task 1 — Adapter: idempotent-by-name `save_script` (AC1)**
  - [ ] In [artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py), rewrite `save_script` ([:143-145](src/ai_qa/pipelines/artifact_adapter.py:143)) to mirror `save_requirement`'s D8 idempotent pattern ([:51-103](src/ai_qa/pipelines/artifact_adapter.py:51)) (and the 12.5 `save_test_case` copy): snapshot prior `kind="playwright_script"` rows with the **same name** BEFORE saving; call `save_artifact(...)` for the new copy first (the per-artifact write is atomic — [service.py:114-137](src/ai_qa/artifacts/service.py:114)); only after the new row commits, best-effort `delete_artifact` the superseded prior rows (log-and-continue on delete failure). Keep the `_schedule_change_event(artifact.id, "created")` broadcast. Return the `Artifact` (callers ignore it today; the metadata task may want `artifact.id`/`storage_path`).

    ```python
    def save_script(self, name: str, script_content: str) -> Artifact:
        """Persist an APPROVED Playwright script under projects/{id}/test_scripts/.

        Idempotent-by-name (D8): keeps a single approved artifact per script name per
        project, so a reject→regenerate→re-approve (or a retried approve) converges to
        exactly one artifact instead of duplicating. The new copy is saved FIRST (the
        per-artifact write is atomic); the superseded prior rows are deleted afterwards
        so a mid-save failure never opens a zero-row window.
        """
        prior = [
            art
            for art in self.service.list_artifacts(
                project_id=self.project_id, kind="playwright_script"
            )
            if art.name == name
        ]
        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind="playwright_script",
            name=name,
            content=script_content,
        )
        for art in prior:
            try:
                self.service.delete_artifact(project_id=self.project_id, artifact_id=art.id)
            except Exception:
                logger.warning(
                    "save_script: could not delete superseded approved artifact %s — "
                    "leaving in place",
                    art.id,
                )
        self._schedule_change_event(artifact.id, "created")
        return artifact
    ```

    > Snippet-fidelity note ([create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)): this **replaces** the one-line `_save_text(kind="playwright_script", ...)` body. The old `save_script` returned `_save_text`'s `Artifact`; the new one returns the new `Artifact` too — no caller signature breaks. Confirm `from ai_qa.db.models import Artifact` is already imported (it is — [artifact_adapter.py:12](src/ai_qa/pipelines/artifact_adapter.py:12)).

- [x] **Task 2 — Agent: fix the `.spec.ts` → `.py` save-name fallback (AC1)**
  - [x] In `SarahAgent.handle_approve`'s script-review branch (13.7's version; on the pre-13.x baseline it is [sarah.py:537-540](src/ai_qa/agents/sarah.py:537)), change the `save_script` filename fallback from `f"{current_script.test_case.filename}.spec.ts"` to `f"{current_script.test_case.filename}.py"` — Sarah generates **Python** Playwright scripts (`_generate_filename` → `test_*.py`, [script_generator.py:436-466](src/ai_qa/pipelines/script_generator.py:436)). The primary name (`Path(script.file_path).name`) is already a `.py` filename; only the fallback was wrong.
  - [x] **Do NOT** touch 13.7's `approved_by`/`approved_at` stamp, the edit/validate gate (13.6), or the `_reviewed_indices` DONE gate (13.5) in this branch. The only change here is the fallback extension.

- [x] **Task 3 — Agent: real, approved-only side-car metadata (AC1, AC2)**
  - [x] Rewrite `_write_approved_scripts_metadata` ([sarah.py:738-756](src/ai_qa/agents/sarah.py:738)) to:
    - **Iterate only approved scripts:** `for script in self._generated_scripts: if not script.approved: continue` (or `for script in (s for s in self._generated_scripts if s.approved)`). This fixes the AC1/AC2 defect that the current code writes metadata for **every** script (skipped/failed/unapproved included).
    - **Build the real side-car** from the `GeneratedScript` fields (narrow `self.project_context is not None` first — already done at the top of the method):

      ```python
      adapter.save_metadata(
          f"{script.test_case.filename}.metadata.json",
          {
              "source_test_case_id": script.source_test_case_id,   # Task 4 — real source TC artifact id
              "logical_path": script.file_path,                    # the .py filename (AC2 "logical path")
              "output_path": saved_storage_path,                   # the saved artifact storage_path (AC2 "output path")
              "approved_by": script.approved_by,                   # 13.7
              "approved_at": script.approved_at,                   # 13.7
              "validation_status": validation_status,              # 13.6 (see Task 0 — reconcile field)
              "model": self.config.model_name,
              "confidence": script.confidence,
              "test_case_title": script.test_case.title,
          },
      )
      ```

    - **`output_path`** = the saved script artifact's `storage_path`. Get it by matching `adapter.load_scripts()` / `list_artifacts(kind="playwright_script")` by `name` (the `.py` filename from Task 2), or by having `handle_approve` stash the `Artifact` returned by the (now `Artifact`-returning) `save_script` on the `GeneratedScript` (e.g. a `saved_artifact_id`/`saved_storage_path` field). **AC2 says "output path OR logical path"** — the `file_path` logical path alone satisfies it; include the storage path only if it's cleanly available (don't add a fragile lookup just for it). Pick the simpler of the two and note the choice.
    - **Remove** the bogus `"source_url": script.test_case.filename` key (a filename is not a URL). If a source URL is genuinely available on the test case (e.g. via 13.2's source attribution), include it as a real `source_url`; otherwise omit it.
  - [x] Keep the method called where 13.5 calls it on DONE (Task 0 located it). Keep the existing per-script `try/except` log-and-continue **only** for the side-car write — but see Saved Q#3 on whether a side-car failure should surface a recovery message instead of being silently swallowed. (The script **content** is already durably saved by `save_script` at approve-time; a side-car failure loses only the audit metadata, not the script.)
  - [x] Replace the stale method docstring ("Write metadata for all approved scripts") to reflect approved-only + real provenance.

- [x] **Task 4 — Capture the source test case artifact ID (AC2)** — see "The source-test-case-artifact-ID gap"
  - [x] If Task 0 found that 13.1/13.2 **already** capture the source test case artifact ID on `GeneratedScript`/`TestCase`, **lift it** in Task 3 (no new field) and skip the rest of this task.
  - [x] If they do **not**, add `source_test_case_id: str | None = None` to `GeneratedScript` ([sarah.py:26-37](src/ai_qa/agents/sarah.py:26)) and **capture it during load/generation**: Sarah's approved-test-case load (13.1's `load_approved_test_cases`, or the legacy `_load_test_cases` → `load_test_cases()` at [sarah.py:208-242](src/ai_qa/agents/sarah.py:208)) returns `PipelineArtifact`s that carry `.id` — thread that id onto each generated script (`GeneratedScript(..., source_test_case_id=str(artifact.id))`). When the id is genuinely unavailable (e.g. a parse-failure placeholder), leave it `None` and the side-car records `null` gracefully.
  - [x] **Boundary:** this is the minimal producer-side capture needed for AC2; do **not** redesign 13.1's loader or 13.2's generation. If the capture would require non-trivial changes to 13.1/13.2 code, flag it and prefer the `None`-tolerant default + a note for a follow-up. (Saved Q#1.)

- [x] **Task 5 — AC3 structural approved-only query reachability (AC3)**
  - [x] Add a code comment at the `save_script` call site (and/or `save_script`'s docstring — Task 1) stating the contract: *"`save_script` runs **only** in the approve path, so every `kind="playwright_script"` artifact under `test_scripts/` is approved by construction. The artifact set IS the Jack-eligibility surface — Story 15.1 (`load_approved_scripts`) queries it project-scoped. Skipped/rejected/regenerated scripts are never persisted as scripts."*
  - [x] **Verify** (no code change expected) that `handle_skip` ([sarah.py:621-666](src/ai_qa/agents/sarah.py:621)) and the reject/regenerate path do **not** call `save_script` — so skipped/rejected scripts are structurally excluded. If any do, flag it. Record in Completion Notes.
  - [x] **Do NOT** add `load_approved_scripts` or any Jack/Epic-15 code (Saved Q#2 — seam left to 15.1).

- [x] **Task 6 — Backend tests (AC1, AC2, AC3)**
  - [x] **Adapter idempotency (AC1)** — extend [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py) (real `ArtifactService` + in-memory SQLite; copy the `save_requirement`/`save_test_case` idempotency test): call `adapter.save_script("test_login.py", "...")` twice with the same name; assert `list_artifacts(project_id=..., kind="playwright_script")` returns exactly **one** row for that name (second save superseded the first). Assert `storage_path` starts with `projects/{project_id}/test_scripts/`.
  - [x] **AC3 query reachability (no workspace path)** — save an approved script via `adapter.save_script("test_login.py", "...")`, then assert `adapter.load_scripts()` (and `service.list_artifacts(kind="playwright_script")`) returns it, `service.read_current_content(artifact)` returns the script bytes, and a **different** project's query returns `[]` (project-scoping). No filesystem `workspace/...` path is constructed. This is the seam **Story 15.1** consumes.
  - [x] **Agent: real, approved-only side-car (AC1, AC2)** — extend [tests/test_agents/test_sarah.py](tests/test_agents/test_sarah.py) (seed `_generated_scripts` with a mix of approved + skipped/unapproved + a failed-placeholder; patch `ai_qa.agents.sarah.PipelineArtifactAdapter` — the scaffold around [test_sarah.py:130-160,310-340](tests/test_agents/test_sarah.py:130)). Drive the DONE path (`_write_approved_scripts_metadata`). Assert:
    - `save_metadata` is called **only** for the approved scripts (not the skipped/failed/unapproved ones) — `save_metadata.call_count == <approved count>`.
    - each call carries the **real** `source_test_case_id` (a uuid string, not the filename), `approved_by`/`approved_at`, `validation_status`, `confidence`, `test_case_title`, `logical_path` (the `.py` filename) — and **not** the literal `source_url == test_case.filename`.
  - [x] **`.py` fallback name (AC1)** — call the approve path with a `GeneratedScript` whose `file_path == ""` (failed/empty) and assert `save_script` is called with `f"{test_case.filename}.py"` (not `.spec.ts`). With a normal `file_path == "test_x.py"`, assert it saves as `test_x.py`.
  - [x] **Regression:** the existing approve/skip/done tests still pass (`test_handle_approve_marks_script_approved_and_advances` [test_sarah.py:422](tests/test_agents/test_sarah.py:422), `test_handle_approve_transitions_to_done_when_all_approved` [:457](tests/test_agents/test_sarah.py:457), `test_handle_approve_presents_next_script` [:489](tests/test_agents/test_sarah.py:489), and the `save_metadata` assertion at [:327](tests/test_agents/test_sarah.py:327) — update it to the real-metadata shape). The save path opens **no** MCP client and calls **no** LLM. Run the **whole** suite `uv run pytest --no-cov` (subset runs trip the coverage gate; prior-epic baseline = 1098 passed — [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). Fix shared-fixture breaks centrally in [tests/conftest.py](tests/conftest.py) ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).

- [x] **Task 7 — Verify (no migration; backend-only)**
  - [x] Backend: `uv run pytest --no-cov` (full suite) green. `uv run mypy src` clean. **Pyrefly-clean:** narrow `self.project_context` (and any `… | None`) before use; `source_test_case_id`/`approved_by`/`approved_at` typed `str | None` — store verbatim (no redundant `str()` on values already `str`); `from ai_qa.db.models import Artifact` already imported; no redundant casts/conversions; no bare `except` where a specific type fits; `pytest.raises` needs a specific type + `match=`.
  - [x] Frontend: `npm run typecheck` clean (**no FE change in 13.8**). `npm run lint`/`npm run test` green (no behavior change). Confirm **no new package** (`git status` on `frontend/package.json`/`package-lock.json`).
  - [x] Confirm **no Alembic migration** — `kind="playwright_script"` → `test_scripts/` mapping exists; 11.7 columns exist; `GeneratedScript` is an in-memory Pydantic model; the script persists as raw text. State explicitly in Completion Notes.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/sarah.py` — Epic-5 implementation; 13.1–13.7 reshape it; 13.8 fixes the save metadata + name + idempotency.**

- **At baseline `79f3f3c`** (pre-13.x): `handle_approve` ([:519-570](src/ai_qa/agents/sarah.py:519)) marks `approved=True`, calls `save_script(Path(file_path).name or f"{...}.spec.ts", content)` ([:537-540](src/ai_qa/agents/sarah.py:537)), advances `_current_review_index`, and on DONE calls `_write_approved_scripts_metadata()` then sends a success message; `_write_approved_scripts_metadata` ([:738-756](src/ai_qa/agents/sarah.py:738)) loops **all** `self._generated_scripts` and writes `{"source_url": script.test_case.filename, "model": ..., "confidence": ..., "test_case_title": ...}`; `handle_skip` ([:621-666](src/ai_qa/agents/sarah.py:621)) advances **without** `save_script`; `GeneratedScript` ([:26-37](src/ai_qa/agents/sarah.py:26)) has no `approved_by`/`approved_at`/`warnings`/`source_test_case_id`.
- **By the time 13.8 starts, 13.1–13.7 have changed this**: `handle_approve` is phase-dispatched + index-addressable, validates + saves the edited-or-original content (13.6), stamps `approved_by`/`approved_at` (13.7), adds to `_reviewed_indices`, DONE when all reviewed; present is the `script_review` present-all transport (13.5). **13.8's insertions are surgical:** (Task 2) one fallback-extension change at the `save_script` call; (Task 3) rewrite `_write_approved_scripts_metadata` (approved-only + real fields); (Task 4) capture `source_test_case_id`; (Task 1) idempotent `save_script` in the adapter. Reconcile against the live (13.1–13.7-merged) shape; **do not delete** the surrounding 13.5/13.6/13.7 logic.

**`src/ai_qa/agents/mary.py` / Story 12.5 — the direct analog.** 12.5 rewrites `_write_approved_test_cases` to populate real side-car metadata + makes `save_test_case` idempotent + proves the query surface. **13.8 is the same shape for Sarah's scripts**, with two differences: (1) the script persists as **raw `.py` text** (no `model_dump_json` content carrier), so the **side-car is the only durable home** for the script-specific provenance (12.5's content also carried it); (2) 13.8 also fixes the `.spec.ts`→`.py` name bug (a Sarah-only defect). 12.5's AC3 added save-failure batch hardening; **13.8's epics.md ACs do NOT include a save-failure recovery AC** (13.8's AC3 is the Jack query reachability, = 12.5's AC2), so failure-hardening is a Saved Question here, not core scope.

**`src/ai_qa/pipelines/artifact_adapter.py` — `save_script` to make idempotent.** `save_script` ([:143-145](src/ai_qa/pipelines/artifact_adapter.py:143)) calls `_save_text(kind="playwright_script")`, which always creates a new row. Copy `save_requirement`'s D8 pattern ([:51-103](src/ai_qa/pipelines/artifact_adapter.py:51)) (or 12.5's `save_test_case` copy of it): snapshot prior same-name rows → save new first (atomic) → delete superseded after. `delete_artifact` ([service.py:211-234](src/ai_qa/artifacts/service.py:211)) is the dedupe primitive.

**`src/ai_qa/artifacts/storage.py` + `service.py` — the save target + atomicity (unchanged).** `build_artifact_key` maps `playwright_script` → `test_scripts/` ([storage.py:34-35](src/ai_qa/artifacts/storage.py:34)); `save_artifact` is per-artifact atomic (DB rollback + storage delete on exception — [service.py:114-137](src/ai_qa/artifacts/service.py:114)); native columns (`created_by_user_id`/`updated_by_user_id`/`thread_id`/`agent_run_id`/`created_at`/`updated_at`) cover 6 of AC2's fields. 13.8 changes neither file.

### The source-test-case-artifact-ID gap (the one genuinely non-obvious design point)

AC2 requires the metadata to include the **source test case artifact ID** — the `Artifact.id` of the `kind="testcase"` artifact the script was generated from. **This is NOT a field any prior 13.x story clearly owns**, and the current code throws it away: `_load_test_cases` ([sarah.py:208-242](src/ai_qa/agents/sarah.py:208)) calls `load_test_cases()` (which returns `PipelineArtifact`s carrying `.id`) but then parses only the JSON **content** into `TestCase` objects and **discards the artifact id** ([sarah.py:225-234](src/ai_qa/agents/sarah.py:225)). So:

- **Best case:** 13.1's `load_approved_test_cases` (the analog of 12.1's `load_approved_requirements`) already keeps the artifact id and threads it onto each `GeneratedScript` (or `TestCase`). Then 13.8 just **lifts** it (Task 4 first bullet). **Check this in Task 0.**
- **Fallback (Task 4 second bullet):** if not, 13.8 adds `source_test_case_id: str | None = None` to `GeneratedScript` and captures `str(artifact.id)` when building each script from its loaded test-case artifact. This is a legitimately-13.8 producer-side addition because 13.8 owns the metadata that needs it — but keep it **minimal** and `None`-tolerant; do not redesign 13.1's loader.

Distinguish this from `source_requirement_id` (12.2): that is the **requirement** the test case came from (Mary's provenance). The **source test case artifact ID** here is the **test case** the script came from (Sarah's provenance) — a different id, one hop downstream. If 13.2's "metadata linking back to the source test case" already records a test-case identifier in the script header/comment, that's a *human-readable* link, not the artifact UUID AC2 wants — still capture the UUID.

### AC2 — the metadata fields, and where each lives

| AC2 field | Where it is stored | Source |
| --- | --- | --- |
| creator | `artifacts.created_by_user_id` (native) | `context.user_id` via `save_script` → `save_artifact(owner_user_id=...)` |
| updater | `artifacts.updated_by_user_id` (native) | same |
| originating thread | `artifacts.thread_id` (native) | `context.thread_id` |
| originating agent run | `artifacts.agent_run_id` (native) | `context.agent_run_id` |
| timestamp | `artifacts.created_at` / `updated_at` (native, `TimestampMixin`) | DB default |
| artifact kind / folder | `artifacts.kind = "playwright_script"` → `test_scripts/` (native) | `save_script` |
| **source test case artifact ID** | **side-car** (`source_test_case_id`) | `GeneratedScript.source_test_case_id` (Task 4) |
| **output / logical path** | **side-car** (`logical_path` = `file_path`; optional `output_path` = `storage_path`) | `GeneratedScript.file_path` / saved `Artifact.storage_path` |
| **approval status** | **side-car** (`approved_by` / `approved_at`) | `GeneratedScript.approved_by`/`approved_at` (13.7) |
| **validation status** | **side-car** (`validation_status`) | 13.6's `validate_script` outcome (reconcile field name) |

So 13.8 adds **no DB column** — the native columns cover 5 fields, and the script-specific fields live in the expanded side-car (`kind="configuration"`). Unlike 12.5 (where the test-case JSON content **also** durably carries source/confidence/approval via `model_dump_json`), a script is raw text, so the **side-car is the sole durable home** for the script-specific provenance — making the "fix the fake side-car" work load-bearing here, not just an audit nicety.

### AC3 — query reachability, and why "only approved" is automatic

AC3 requires saved scripts to be reachable through **project-scoped artifact queries** with **no workspace path**, returning **only approved** scripts. That surface already exists and needs no new endpoint:

- Backend: `ArtifactService.list_artifacts(project_id, kind="playwright_script")` + `read_current_content(artifact)`; `PipelineArtifactAdapter.load_scripts()` ([artifact_adapter.py:147-149](src/ai_qa/pipelines/artifact_adapter.py:147)) wraps it. Storage reads go through `ArtifactStorage` keyed by `storage_path` — never a raw `workspace/` path.
- API: `GET /projects/{id}/artifacts?kind=playwright_script`, `/tree` (the `test_scripts` folder — [storage.py:57-58](src/ai_qa/artifacts/storage.py:57)), `/{artifact_id}`, `/{artifact_id}/content`.

**"Only approved" is structural, not filtered.** Like test cases (no draft test case — [12.5 Dev Notes](_bmad-output/implementation-artifacts/12-5-test-case-artifact-save.md)), there is **no draft script**: `save_script` runs **only** in the approve path; skip/reject/regenerate never persist a script. So every `kind="playwright_script"` artifact is approved by construction; **Story 15.1** can `list_artifacts(kind="playwright_script")` directly with **no** discriminator. (If a future story ever persists a pre-approval draft script, it must add a discriminator — note this for 15.1, don't build it here.)

### Idempotency — why one-per-test-case needs it

AC1 says "one approved script artifact is saved per source test case". In the 13.x model, `save_script` is called **per-approve**. The reject→regenerate→re-approve flow (13.7) and a retried approve both re-call `save_script` with the **same filename**. Without idempotency-by-name, each re-approve appends a **new** `Artifact` row → duplicates → AC1 violation + a confusing tree for Jack. The D8 pattern (save-new-first-then-delete-old) converges to exactly one row per name with **no zero-row window** (so a concurrent Jack read never sees the script vanish mid-save). This is the same guarantee `save_requirement` got in 11.8 and `save_test_case` in 12.5.

### Architecture compliance (hard rules)

- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518,533](_bmad-output/planning-artifacts/architecture.md:518)). 13.8 adds **no** storage access; the script + side-car save through `save_script`/`save_metadata` → `ArtifactService`. No `workspace/...` path is constructed.
- **Sarah flow** `script_generator.py → ai_connection + browser/agent.py → projects/{project_id}/test_scripts/` ([architecture.md:824-828](_bmad-output/planning-artifacts/architecture.md:824)) — unchanged; 13.8 only fixes the save name, the side-car content, and idempotency.
- **No credential/secret leakage** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md), [architecture.md:362-373](_bmad-output/planning-artifacts/architecture.md:362)): the side-car carries only `source_test_case_id` (a UUID), paths, `approved_by` (email/id), `validation_status`, `model` name, `confidence`, title. **Never** put MCP/LLM tokens, raw script bodies-with-secrets, cookies/session tokens (13.4's concern, upstream), or config dicts into the side-car/columns/logs. The script body is saved by `save_script` as-is (13.4 already scrubs secrets from the body); 13.8 adds no secret-bearing field. Leak-canary tests must stay green.
- **Mandatory human review / no auto-advance / no bulk approve** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271)) — 13.8 changes none of the review semantics (13.5/13.7 own them); it only changes persistence. No "Are you sure?" modal.
- **Full-stack sync** — **N/A for 13.8** (backend-only; no payload/TS change). The 13.7 `ScriptReviewItem` sync is unchanged. Run `npm run typecheck` only to confirm nothing broke.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Pyrefly-clean: narrow `self.project_context` / `context.artifact_service` / `context.project_id` (`… | None`) before use; `source_test_case_id`/`approved_by`/`approved_at` are `str | None` — store verbatim, don't `str()` a value already `str` (Pyrefly `unnecessary-type-conversion`); only `str(artifact.id)` (a `UUID`) needs conversion; no redundant casts; no bare `except Exception` where a specific type fits (the idempotent-delete `try/except` is a best-effort recovery, so a broad catch + `logger.warning` is acceptable there, matching `save_requirement`). The agent path uses a **sync** artifact `Session`. `pytest.raises` needs a specific type + `match=`.
- **Frontend:** **no change** — `npm run typecheck`/`lint`/`test` only confirm nothing broke. No new packages.

### Project Structure Notes

- **New files:** none required (extends existing). New/extended tests only.
- **Modified files (expected):** `src/ai_qa/pipelines/artifact_adapter.py` (`save_script` idempotent-by-name), `src/ai_qa/agents/sarah.py` (`.spec.ts`→`.py` fallback; `_write_approved_scripts_metadata` rewritten approved-only + real metadata; possibly `GeneratedScript.source_test_case_id` + its capture in the load/generate path — Task 4), `tests/test_agents/test_sarah.py`, `tests/pipelines/test_pipeline_artifact_adapter.py`.
- **No backend route/schema/REST changes, no new WS action, no frontend file.** **No Alembic migration** (existing kind mapping + columns; in-memory model; raw-text artifact).

### Testing standards summary

- Backend agent: `@pytest.mark.asyncio`; patch `ai_qa.agents.sarah.PipelineArtifactAdapter` at the class boundary; seed `_generated_scripts` with a mix (approved / skipped / failed-placeholder) and assert `save_metadata.call_args_list` carries **real** fields for **approved-only** scripts; assert the `.py` fallback name; assert no LLM/MCP call on the save path.
- Adapter / AC3 / idempotency: real `ArtifactService` over in-memory SQLite with project/user fixtures (copy `tests/pipelines/test_pipeline_artifact_adapter.py`); assert `storage_path` under `projects/{id}/test_scripts/`, `load_scripts()` round-trips, same-name re-save yields exactly one row, cross-project query returns `[]`.
- Frontend: no new component; backend-only — `npm run typecheck`/`lint`/`test` stay green.
- A full Playwright E2E is **not** required (consistent with 12.5 / 11.7 — reaching DONE needs live LLM generation, not E2E-reproducible without a provider key; `page.route` mocking is forbidden — [project-context.md#Testing-Rules](project-context.md)). Backend pytest is the guardrail. Document any deferral in Completion Notes.

### Previous-story / sibling intelligence

- **Story 12.5 (test case artifact save)** — the **direct analog** (`ready-for-dev`): real side-car metadata, idempotent `save_test_case`, query reachability, no migration, backend-only. 13.8 re-applies all of it to scripts. **Differences:** (1) script = raw text → side-car is the sole durable home (no JSON content carrier); (2) 13.8 also fixes the `.spec.ts`→`.py` name bug; (3) 12.5's AC3 = save-failure hardening, but **13.8's epics.md ACs have no save-failure AC** (13.8 AC3 = Jack query reachability), so failure-hardening is a Saved Question, not core scope.
- **Story 11.7 (requirements artifact save, `done`)** — the original of the pattern: authoritative on-approve save, idempotent-by-name (D8 via 11.8), audit side-car, AC3 query reachability proven, `delete_artifact` for dedupe. Reuse the same shape.
- **Story 11.8 / D8 (`done`)** — made `save_requirement` idempotent-by-name (save-new-first-then-delete-old, no zero-row window). Task 1 copies this into `save_script`.
- **Story 13.7 (`ready-for-dev`)** — stamps `GeneratedScript.approved_by`/`approved_at` and **explicitly fences to 13.8**: "lifts `approved_by`/`approved_at` + source test case artifact ID + approval status + validation status into the durable artifact-save metadata/sidecar, adds save idempotency/D8, and fixes the `.spec.ts` fallback + the `_write_approved_scripts_metadata`-writes-all-scripts bug." 13.8 delivers exactly that. 13.7 also noted the misleadingly-named `_write_approved_scripts_metadata` writes a `kind="configuration"` side-car for **every** script — not an AC3 violation (Jack queries `playwright_script`, not `configuration`) but wrong metadata → 13.8 fixes it.
- **Story 13.6 (`ready-for-dev`)** — `validate_script` + validation status; 13.8 lifts the validation status into the side-car (reconcile the field name).
- **Story 13.1 (`ready-for-dev`)** — the approved-test-case loader; the place the **source test case artifact ID** is (or should be) captured. 13.8 lifts it or adds the minimal capture (Task 4).
- **Story 15.1 (Jack — approved-script input selection, `backlog`)** — the consumer of AC3: `load_approved_scripts` (analog of 13.1's `load_approved_test_cases`) filters/queries the approved script artifacts 13.8 guarantees. Keep the producer-side surface clean + documented so 15.1 just reads it (the third instance of the `12.1 → 13.1 → 15.1` "load approved {X}" pattern).
- **Epic 5 (Sarah, `done`)** — built `GeneratedScript`, the review loop, `save_script`, `_write_approved_scripts_metadata`. 13.8 fixes the save metadata/name/idempotency; it changes neither generation nor the review semantics.

### Git intelligence (recent work patterns)

Recent commits (`79f3f3c epic 11 can read confluence page`, `2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`) are Epic 10/11. **Epic 12 (12.1–12.5) and Stories 13.1–13.7 are NOT implemented** — the live `sarah.py`/`artifact_adapter.py`/`GeneratedScript`/`ScriptGenerator` are pre-13.x (verified at `79f3f3c`: `handle_approve` saves the original with the `.spec.ts` fallback, no phase-dispatch/`_reviewed_indices`/`script_review`/`SarahScriptReviewPanel`; `_write_approved_scripts_metadata` writes a fake side-car for all scripts; `save_script` is non-idempotent; `GeneratedScript` has no `approved_by`/`approved_at`/`warnings`/`source_test_case_id`). **13.8 is blocked until 13.1–13.7 (and the 12.5 `save_test_case` idempotency) land** — verify in the live tree (Task 0) and flag/stop if unmerged rather than re-implementing upstream. The established pattern (11.7/11.8/12.5): artifact metadata in PostgreSQL + bytes in storage, idempotent-by-name saves (save-new-first-then-delete-old), atomic `save_artifact` with a fire-and-forget change event, `delete_artifact` for dedupe. 13.8 follows it exactly. Closest code to copy: [12-5-test-case-artifact-save.md](_bmad-output/implementation-artifacts/12-5-test-case-artifact-save.md) (the save analog), `save_requirement` ([artifact_adapter.py:51-103](src/ai_qa/pipelines/artifact_adapter.py:51)) (the D8 idempotency reference).

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1411-1430] — Story 13.8 ACs (save under `projects/{project_id}/test_scripts/`, one per source test case; metadata incl. source test case artifact ID / output-or-logical path / approval status / creator / updater / thread / agent-run / validation status / timestamp; project-scoped approved-only Jack queries); Epic 13 intro + FRs (1253-1257); siblings 13.5 review UX (1345-1365), 13.6 edit (1367-1387), 13.7 approve/reject/regenerate (1389-1409); Story 12.5 (the analog, 1231-1251)
- [Source: _bmad-output/planning-artifacts/prd.md] — generated-script spec (Python/Playwright/assertions/stable selectors, 309-316); security / no-secrets-in-scripts (237-243, 465-475); artifact persistence + project scoping
- [Source: _bmad-output/planning-artifacts/architecture.md] — agents never touch storage directly (518, 533); Sarah flow → `test_scripts/` (824-828); project-scoped artifact folders + metadata field list incl. creator/updater/thread/agent-run/timestamps (280, 336-360); security / no-secret-leakage (362-373)
- [Source: src/ai_qa/agents/sarah.py] — `GeneratedScript` (26-37); `handle_approve` save + `.spec.ts` fallback (519-570, save 537-540); `handle_skip` no-save (621-666); `_write_approved_scripts_metadata` writes-all-with-fake-`source_url` (738-756); `_load_test_cases` discards artifact id (208-242, parse 225-234)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `save_script` to make idempotent (143-145); `save_requirement` D8 idempotent reference (51-103); `save_test_case` (134-137, 12.5 makes it idempotent — the closest copy); `load_scripts` AC3 seam (147-149); `save_metadata` (151-157); `_save_text` (202-213); `_load_text_artifacts`/`_to_pipeline_artifact` (245-257); `PipelineArtifact.id` (22)
- [Source: src/ai_qa/artifacts/storage.py] — `build_artifact_key` `playwright_script`/`testscript` → `test_scripts/` (28-38, 34-35); `folder_for_kind` (41-60, 57-58)
- [Source: src/ai_qa/artifacts/service.py] — `save_artifact` atomic write + native creator/updater/thread/agent-run/timestamp columns (74-140); `delete_artifact` (211-234, dedupe/rollback primitive); `list_artifacts(project_id, kind)` (194-201); `read_current_content` (236-238); `ARTIFACT_KINDS` incl. `playwright_script` (17-31)
- [Source: src/ai_qa/pipelines/script_generator.py] — `generate` (64); `_generate_filename` → `test_*.py` (436-466, confirms `.py` not `.spec.ts`); `_generate_script_header` (468)
- [Source: src/ai_qa/models.py] — `TestCase` + `filename` property (265-298); `TestCaseStep` (244-262)
- [Source: src/ai_qa/pipelines/context.py] — `PipelineContext` (`user_id`/`user_email`/`project_id`/`thread_id`/`agent_run_id`/`artifact_service`) — provenance threaded into `save_artifact`
- [Source: tests/test_agents/test_sarah.py] — Sarah test scaffold (patch adapter 130-160; `save_metadata` assertion 327; approve/done/next tests 422-510)
- [Source: tests/pipelines/test_pipeline_artifact_adapter.py] — real-service in-memory SQLite scaffold (AC3 + idempotency)
- [Source: _bmad-output/implementation-artifacts/12-5-test-case-artifact-save.md] — the direct analog (idempotent save, real side-car, query reachability, no migration, backend-only)
- [Source: _bmad-output/implementation-artifacts/11-7-requirements-artifact-save.md] + 11-8 (D8) — the original save + idempotency pattern
- [Source: _bmad-output/implementation-artifacts/13-7-script-approval-rejection-and-regeneration.md] — the explicit fence: `.spec.ts` + writes-all-scripts + idempotency + durable metadata lift all = 13.8
- [Source: _bmad-output/implementation-artifacts/13-1-approved-test-case-input-selection.md] — the loader where the source test case artifact ID is (or should be) captured
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional, no redundant cast/conversion); no bare except; no `# type: ignore`; security (no secret/HTML/config in fields/logs); full-stack sync (N/A here)

### Definition of Done

- [x] Approved scripts are saved under `projects/{project_id}/test_scripts/` (existing `kind="playwright_script"` mapping) with the **`.py`** save name (the `.spec.ts` fallback is gone), and `save_script` is **idempotent-by-name** so a re-approval yields exactly **one** artifact per script name (AC1).
- [x] The side-car carries **real** `source_test_case_id`, `logical_path` (+ optional `output_path`), `approved_by`/`approved_at`, `validation_status`, `model`, `confidence`, `test_case_title`; it is written for **approved scripts only** (skipped/failed/unapproved excluded); the bogus `source_url == test_case.filename` is gone; native columns cover creator/updater/thread/agent-run/timestamp (AC2).
- [x] Saved scripts are reachable via `load_scripts()` / `list_artifacts(kind="playwright_script")` / the artifact API, project-scoped, **no** workspace-path read; only approved scripts exist (no draft); the seam Jack/15.1 will consume is proven by a test (AC3).
- [x] No Alembic migration (confirmed); no new frontend component; no TS interface change (13.7 already synced `ScriptReviewItem`).
- [x] Existing Sarah approve/skip/done tests pass (updated to the real-metadata shape); the save path opens no MCP client and calls no LLM; leak-canary tests green.
- [x] New tests: idempotent-retry convergence (one row per name), AC3 query reachability (project-scoped, no workspace path), real approved-only side-car metadata, `.py` fallback name.
- [x] `uv run pytest --no-cov` green; `uv run mypy src` clean (Pyrefly-clean); `npm run typecheck`/`lint`/`test` green in `/frontend`.

---

## Saved Questions (for Thuong — confirm or correct)

1. **Source test case artifact ID — where captured?** Default = **lift it from `GeneratedScript` if 13.1/13.2 already capture it; otherwise 13.8 adds a `None`-tolerant `source_test_case_id: str \| None` to `GeneratedScript` and captures `str(artifact.id)` during the approved-test-case load** (the load already returns `PipelineArtifact`s with `.id`; the current code just discards it). Alternative = require 13.1 to own the capture and have 13.8 only lift (cleaner ownership, but blocks 13.8 if 13.1 didn't do it). Take the backstop default so AC2 is satisfiable regardless of 13.1's exact shape?
2. **Do NOT pre-build Jack's `load_approved_scripts` seam (Epic 15).** Default = AC3 is a producer-side structural guarantee (only approved script content reaches `test_scripts/`) + a documented contract; **Story 15.1** adds the `load_approved_scripts` loader (the `12.1→13.1→15.1` pattern). 13.8 writes no Jack code and no loader. Alternative = add a read-only `load_approved_scripts` now (harmless but untested-in-context until Epic 15 + invites scope creep). Keep the seam for 15.1?
3. **Save-failure hardening — match 12.5 or stay minimal?** 13.8's epics.md ACs have **no save-failure recovery AC** (13.8 AC3 = Jack query reachability, not 12.5's failure-recovery AC3). Default = **stay minimal**: the script **content** is durably saved per-approve by `save_script` (atomic), and idempotency + per-approve independence cover retries — so 13.8 does **not** add 12.5-style batch rollback. The only adjustment: don't let a side-car write failure silently masquerade as full success (log it; the script content is already safe). Alternative = add full 12.5-style hardening (gate DONE/success on save result, UX-DR12 retry message, stay reviewable) for parity even though no AC mandates it. Stay minimal, or add parity hardening?
4. **Side-car `output_path` (storage path) or logical path only?** AC2 says "output path **or** logical path". Default = record the **logical path** (`file_path`, the `.py` filename) always, and include the storage `output_path` only if it's cleanly available (e.g. by stashing the `Artifact` returned by `save_script`) — don't add a fragile name-lookup just for it. Alternative = always record both (needs threading the saved `Artifact` from `handle_approve` into the DONE-time metadata). Keep logical-path-default?
5. **Script E2E coverage.** Default = backend pytest is the guardrail; **no** Playwright E2E for the save (reaching DONE needs live LLM generation, not E2E-reproducible without a provider key; `page.route` mocking forbidden) — same rationale as 12.5/11.7. Acceptable, or attempt an E2E against a stub provider if one is available in the E2E env?

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

(none — clean run, no dead-ends or retries)

### Completion Notes List

**Task 0 — Prerequisite verification:**
- 13.1–13.7 and 12.5 all confirmed merged in the working tree (`src/ai_qa/agents/sarah.py` has `GeneratedScript.approved_by`/`approved_at`, phase-dispatched `handle_approve`, `_reviewed_indices` DONE gate, `_write_approved_scripts_metadata` called from DONE path, `validate_script` gate, and `_confirmed_test_cases`/`confirmed_test_cases`).
- 13.1's `_confirm_inputs` returns `PipelineArtifact` objects but discards `.id` when parsing test cases into `TestCase` — the source-test-case-artifact-ID gap confirmed. Task 4 adds `source_test_case_id` to `GeneratedScript` + a parallel `_test_case_source_ids` list.
- 13.6's validation status recorded as `validation_status: str | None` on `GeneratedScript` (set to `"validated"` when edit passes the gate).
- Reference for Task 1: copied `save_test_case` D8 pattern (12.5's form — closest mirror).

**Task 1 — `save_script` idempotent-by-name (D8):**
- Rewrote `save_script` from one-line `_save_text(kind="playwright_script", ...)` to the D8 pattern: snapshot prior same-name rows → save new first → delete superseded after. Returns `Artifact`.
- Docstring documents the AC3 structural guarantee for Story 15.1.

**Task 2 — `.spec.ts` → `.py` fallback:**
- Single-character change in `handle_approve`'s `save_script` call: fallback changed from `f"{current_script.test_case.filename}.spec.ts"` to `f"{current_script.test_case.filename}.py"`.

**Task 3 — `_write_approved_scripts_metadata` rewritten approved-only + real fields:**
- Iterates `self._generated_scripts` with `if not script.approved: continue` guard.
- Side-car fields: `source_test_case_id`, `logical_path` (`file_path`), `approved_by`, `approved_at`, `validation_status`, `model`, `confidence`, `test_case_title`.
- Removed bogus `source_url: script.test_case.filename` key.
- AC2 "output path OR logical path" satisfied via `logical_path` alone (Saved Q#4 default: no fragile `storage_path` lookup added).

**Task 4 — `source_test_case_id` capture:**
- Added `source_test_case_id: str | None = None` and `validation_status: str | None = None` fields to `GeneratedScript`.
- Added `self._test_case_source_ids: list[str | None] = []` parallel list to `SarahAgent.__init__`.
- `_confirm_inputs` populates the parallel list with `str(art.id)` for each test case parsed from the `PipelineArtifact`.
- Fallback path (`_load_test_cases`) initializes `_test_case_source_ids = [None] * len(self._test_cases)`.
- `_generate_scripts` changed from `enumerate(start=1)` to 0-based with `i = idx + 1` for display, and looks up `source_tc_id` via 0-based index.
- `validation_status = "validated"` set in `handle_approve` when edited content passes `validate_script`.

**Task 5 — AC3 structural guarantee:**
- Verified `handle_skip` and reject/regenerate paths do NOT call `save_script` — AC3 structural guarantee holds.
- Docstring in `save_script` explicitly documents the contract for Story 15.1.
- No `load_approved_scripts` added (Saved Q#2 default: seam left for 15.1).

**No Alembic migration:** `kind="playwright_script"` → `test_scripts/` mapping already exists (`storage.py:34-35`); 11.7 provenance columns exist; `GeneratedScript` is an in-memory Pydantic model; script persists as raw `.py` text.

**No frontend change:** `npm run typecheck`/`lint`/`test` all clean; `ScriptReviewItem` TS interface already synced by 13.7; no new packages.

**Test results:** 1388 passed, 1 warning (full suite `uv run pytest --no-cov`). `uv run mypy src` clean (no issues in 80 source files). 95 story-targeted tests pass (14 new in `TestSarahArtifactSave138` + 3 new adapter tests + existing regressions all green).

**Saved Q decisions:** Q#1 default taken (added `source_test_case_id` to `GeneratedScript`); Q#2 default taken (no `load_approved_scripts`); Q#3 default taken (minimal — no batch rollback, side-car failure logged and continued); Q#4 default taken (logical path only); Q#5 default taken (no Playwright E2E).

### File List

- `src/ai_qa/pipelines/artifact_adapter.py` — `save_script` rewritten to D8 idempotent-by-name pattern (Task 1)
- `src/ai_qa/agents/sarah.py` — `GeneratedScript` + `source_test_case_id`/`validation_status` fields; `SarahAgent._test_case_source_ids`; `.spec.ts`→`.py` fallback; `_confirm_inputs` captures parallel source-ID list; `_generate_scripts` 0-based indexing + `source_test_case_id` wiring; `handle_approve` sets `validation_status="validated"` on edit; `_write_approved_scripts_metadata` rewritten approved-only + real metadata (Tasks 2, 3, 4)
- `tests/pipelines/test_pipeline_artifact_adapter.py` — 3 new tests: idempotent-by-name, AC3 query reachability, cross-name independence (Task 6)
- `tests/test_agents/test_sarah.py` — 11 new tests in `TestSarahArtifactSave138`: approved-only metadata, real provenance fields, `.py` fallback, `source_test_case_id` wiring, `validation_status` stamping (Task 6)

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-06-17 | 1.0 | Story implemented: D8 idempotent `save_script`, `.spec.ts`→`.py` fix, real approved-only side-car, `source_test_case_id` capture | claude-sonnet-4-6 |
