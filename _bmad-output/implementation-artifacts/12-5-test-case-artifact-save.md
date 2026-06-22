---
baseline_commit: b4ce65f
---

# Story 12.5: Test Case Artifact Save

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want approved generated test cases saved as project artifacts with complete provenance metadata, and the save hardened against failure,
so that Sarah and other project members can use them as shared, project-scoped automation inputs without ever consuming a partial or unapproved set.

## Acceptance Criteria

Verbatim from [epics.md#Story-12.5](_bmad-output/planning-artifacts/epics.md) (lines 1231-1251), expanded with implementation defaults (see "Scope decisions" — confirm or correct).

### AC1 — Approved test case is saved under `projects/{project_id}/test_cases/` with full metadata

- **Given** a generated test case is approved
- **When** Mary saves it
- **Then** the artifact service stores it under `projects/{project_id}/test_cases/`
- **And** artifact metadata includes **source requirement artifact IDs**, **confidence data** (score + level + rationale), **approval status** (approved_by + approved_at), **creator**, **updater**, **originating thread**, **originating agent run**, and **timestamp**.

### AC2 — Saved test cases are reachable through project-scoped artifact queries (no workspace paths)

- **Given** saved test case artifacts exist
- **When** Sarah (or a project member) requests approved test cases for the selected project
- **Then** only project-scoped approved test case artifacts are returned through artifact service queries
- **And** direct workspace path reads are not used.

### AC3 — Save failure does not leave partial output approved/available and yields a clear recovery message

- **Given** saving fails
- **When** Mary reports the failure
- **Then** partial output is **not** marked approved or made available to Sarah (no partial test-case set is left in `test_cases/`)
- **And** the user receives a clear retry or recovery message
- **And** Mary does **not** transition to `DONE` — the test cases stay reviewable so the user can re-approve and retry the save.

---

## ⚠️ CRITICAL: This story makes the on-DONE test-case save AUTHORITATIVE, FULLY-PROVENANCED, and FAILURE-SAFE — it is the test-case analog of Story 11.7

By the time control reaches this story, Mary already saves approved test cases. After **12.1–12.4** merge, the per-item review loop approves every test case and, at `DONE`, `MaryAgent._write_approved_test_cases` writes each `TestCase` as `kind="testcase"` JSON plus a `{filename}.metadata.json` side-car. **But that save has three defects this story fixes:**

1. **The side-car metadata is fake.** It hardcodes `"source_url": ""` and **`"confidence": 1.0`** ([mary.py:295-303](src/ai_qa/agents/mary.py:295)) and omits the source requirement id, the real confidence band/rationale, and the approval stamp. (The `1.0` hardcode was explicitly flagged as **12.5's to reconcile** by [12.3 Saved Q#3](_bmad-output/implementation-artifacts/12-3-confidence-scoring-for-generated-test-cases.md) and [12.4 sibling note](_bmad-output/implementation-artifacts/12-4-mary-review-workflow.md).)
2. **The save swallows failure.** The per-case `try/except` ([mary.py:304-305](src/ai_qa/agents/mary.py:304)) only `logger.error`s and continues; `handle_approve` then transitions to `DONE` and sends a `"N test cases saved"` **success** message **even if every save failed** ([mary.py:147-157](src/ai_qa/agents/mary.py:147)). That is a direct AC3 violation.
3. **`save_test_case` is not idempotent-by-name.** Unlike `save_requirement` (made idempotent in 11.8/D8), `save_test_case` ([artifact_adapter.py:134-137](src/ai_qa/pipelines/artifact_adapter.py:134)) always creates a **new** row, so a retry after a partial failure duplicates test-case artifacts.

Story 12.5 does exactly four things and **nothing else**:

1. **Populate real save metadata (AC1).** Rewrite the side-car to carry the **real** values lifted from each saved `TestCase`: `source_requirement_id` / `source_requirement_name` / `source_url` (12.2), `confidence` / `confidence_level` / `confidence_rationale` (12.3), `approved_by` / `approved_at` (12.4), `model`, `test_case_title`. The native `Artifact` columns already record **creator** (`created_by_user_id`), **updater** (`updated_by_user_id`), **thread** (`thread_id`), **agent run** (`agent_run_id`), and **timestamp** (`created_at`/`updated_at`) — set by `save_test_case` → `save_artifact`. The durable copy of source/confidence/approval is **also** in the test-case JSON content itself (`model_dump_json`).
2. **Harden the save against failure (AC3).** Make `_write_approved_test_cases` failure-aware (returns `bool`); on any per-case save failure, best-effort **roll back** every artifact saved *in this batch* (all-or-nothing → no partial set left), surface a UX-DR12 retry message, and have `handle_approve` **not** transition to `DONE` and **not** send the success message — the cases stay reviewable so re-approving retries the save.
3. **Make `save_test_case` idempotent-by-name (AC3 belt-and-suspenders).** Mirror `save_requirement`'s D8 pattern (snapshot prior rows with the same name → save the new copy first → delete the superseded rows after) so a retry after a transient failure converges to exactly N test-case artifacts instead of duplicating.
4. **Confirm + prove the project-scoped query surface (AC2).** `kind="testcase"` already maps to `projects/{id}/test_cases/` and is listable via `ArtifactService.list_artifacts(kind="testcase")` / `PipelineArtifactAdapter.load_test_cases()` with **no** workspace path. Prove it with a test; Sarah's actual input-selection loader is **Story 13.1**, not this story.

### Confirmed scope decisions (defaults — Thuong confirms or corrects via Saved Questions)

- **No new DB columns / no Alembic migration.** The 11.7 provenance columns (`source_type`, `source_url`, `warnings`) already exist (migration `c8e6ace95b08`); `TestCase` persists via `model_dump_json` (Pydantic, not a DB table); the `kind="testcase"` → `test_cases/` storage mapping already exists. **State this explicitly in Completion Notes** (mirrors 12.1–12.4).
- **Metadata carrier = the test-case JSON content + the expanded side-car + the native columns** (Saved Question #1 lets Thuong additionally stamp the generic 11.7 row columns for queryability). The content (`model_dump_json`) is the authoritative durable record of source-id/confidence/approval; the side-car is the human-readable audit (mirrors 11.7's column-vs-side-car relationship).
- **AC3 partial-failure semantics = all-or-nothing within a batch + idempotent retry** (Saved Question #2). On any save failure, roll back this batch's saves so Sarah can never see a partial set, and make retries converge via idempotent-by-name.

### In scope

- **Agent:** `MaryAgent._write_approved_test_cases` rewritten — real side-car metadata (AC1), `bool` success return + all-or-nothing batch rollback on failure (AC3), stale-docstring cleanup. `MaryAgent.handle_approve` `DONE` branch checks the save result and on failure surfaces a UX-DR12 retry message + stays reviewable (no `DONE`, no success message).
- **Adapter:** `PipelineArtifactAdapter.save_test_case(...)` made idempotent-by-name (mirror `save_requirement`); optionally extended to stamp the generic provenance columns (Saved Question #1).
- **Tests:** real side-car metadata round-trip (AC1), AC2 query reachability via `load_test_cases()` (no workspace path), AC3 save-failure-keeps-reviewable + no-DONE + no-success + no-partial-set, idempotent-retry convergence, plus regression on the existing `handle_approve`/save tests.

### Out of scope (do NOT build)

- **No Sarah / Epic 13 consumption logic.** AC2's "Sarah requests approved test cases" is satisfied by the **query reachability** (test cases listable/readable by project + `kind="testcase"`, no workspace path). The actual input-selection loader (`load_approved_test_cases` — the analog of 12.1's `load_approved_requirements`), thread-prioritization, and the Sarah confirm UI are **Story 13.1**. Do not build Sarah's loader here — just prove the query surface returns approved test cases.
- **No generation / confidence / review-UI changes.** Generation = 12.2, confidence engine = 12.3, the rich review card + approval stamping + Proceed-to-Sarah = 12.4. 12.5 only changes how the **already-approved** set is **persisted, hardened, and queried**.
- **No new frontend component and no TS interface change.** The retry/recovery message rides the existing WebSocket `error` channel (same UX-DR12 pattern Bob uses); the `TestCase` TS interface (incl. `approved_by`/`approved_at`/confidence) was already created/synced in 12.4. Run `npm run typecheck` only to confirm nothing broke.
- **No change to `save_artifact`'s atomic write, `create_version`, the WebSocket router, secret resolution, or the MCP/LLM paths.** The save path opens no MCP client and calls no LLM.
- **No new "approved" discriminator column for test cases.** Unlike requirements (which have a pre-approval **draft** + an approved copy, discriminated by `source_type IS NOT NULL`), there is **no** draft test case — `_write_approved_test_cases` runs only at `DONE`, so every `kind="testcase"` artifact is approved by construction. AC2's "only approved" is therefore satisfied structurally; no discriminator is needed (note this in Dev Notes for 13.1).

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `kind="testcase"` → storage key `projects/{project_id}/test_cases/{artifact_id}/v{version}/{name}` | [src/ai_qa/artifacts/storage.py:32-33](src/ai_qa/artifacts/storage.py) | ✅ done — **AC1 path is already correct; no storage change** |
| `MaryAgent._write_approved_test_cases` (saves each `TestCase` JSON + a side-car) | [src/ai_qa/agents/mary.py:285-305](src/ai_qa/agents/mary.py) | ⚠️ exists — **rewrite: real metadata (AC1) + failure-safe `bool` return + batch rollback (AC3) + cleanup stale docstring** |
| `MaryAgent.handle_approve` `DONE` branch (`_write...` → `DONE` → success msg) | [src/ai_qa/agents/mary.py:138-161](src/ai_qa/agents/mary.py) **(12.4 reshapes this to the index-addressable `_reviewed_indices` model)** | ⚠️ exists — **gate `DONE`/success on the save result; on failure send retry + stay reviewable (AC3)** |
| `PipelineArtifactAdapter.save_test_case(name, content)` → `_save_text(kind="testcase")` | [src/ai_qa/pipelines/artifact_adapter.py:134-137](src/ai_qa/pipelines/artifact_adapter.py) | ⚠️ exists — **make idempotent-by-name (mirror `save_requirement`); optionally accept provenance (Saved Q#1)** |
| `PipelineArtifactAdapter.save_requirement` — idempotent-by-name reference (snapshot prior → save new first → delete superseded) | [src/ai_qa/pipelines/artifact_adapter.py:51-103](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done — **copy this D8 pattern into `save_test_case`** |
| `PipelineArtifactAdapter.load_test_cases()` → `_load_text_artifacts(kind="testcase")` (project-scoped, no workspace path) | [src/ai_qa/pipelines/artifact_adapter.py:139-141,234-246](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done — **AC2 query seam; prove it with a test (13.1 consumes it)** |
| `ArtifactService.save_artifact(...)` — atomic write (DB rollback + storage delete on exception); already accepts `source_type`/`source_url`/`warnings` (11.7) | [src/ai_qa/artifacts/service.py:74-140](src/ai_qa/artifacts/service.py) | ✅ done — **no change; per-artifact atomicity underpins AC3** |
| `ArtifactService.delete_artifact(*, project_id, artifact_id) -> bool` | used by `save_requirement` / `delete_draft_requirement` ([artifact_adapter.py:94,120](src/ai_qa/pipelines/artifact_adapter.py)) | ✅ done — **reuse for the AC3 batch rollback + the idempotent dedupe** |
| `PipelineArtifactAdapter.save_metadata(name, dict)` → `kind="configuration"` JSON side-car | [src/ai_qa/pipelines/artifact_adapter.py:151-157](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done — **reuse for the expanded side-car** |
| `PipelineContext` (`user_id`, `user_email`, `project_id`, `thread_id`, `artifact_service`, `agent_run_id`) | [src/ai_qa/pipelines/context.py](src/ai_qa/pipelines/context.py) | ✅ done — provenance source threaded into `save_artifact` by the adapter |
| `_format_error_message(errors)` — UX-DR12 three-part error | [src/ai_qa/agents/base.py](src/ai_qa/agents/base.py) | ✅ done — **reuse for the AC3 retry message** (mirror 11.7's Bob save-failure message) |
| `TestCase` model (source/confidence/approval fields after 12.2–12.4) + `filename` property | [src/ai_qa/models.py:265-298](src/ai_qa/models.py) | ✅ (after 12.2–12.4) — **read the real fields for the side-car; persists via `model_dump_json`** |
| `ArtifactResponse` / detail / tree expose `source_type`/`source_url`/`warnings` (11.7) | [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py) | ✅ done — **no API change; test-case rows ride the same generic response** |
| Frontend `TestCase` TS interface incl. `approved_by`/`approved_at`/confidence (12.4) | `frontend/src/types/testcase.ts` (created by 12.1, completed by 12.4) | ✅ (after 12.4) — **no FE change in 12.5; `npm run typecheck` only** |

---

## Sequencing dependency (READ FIRST — critical)

**Story 12.5 is the LAST story in the `12.1 → 12.2 → 12.3 → 12.4 → 12.5` chain. Stories 12.1–12.4 are `ready-for-dev`, NOT `done`.** As of this writing the working tree holds the **pre-12.1** Mary and `TestCase` (verified against live code on `b4ce65f` + uncommitted Epic 11):

- `src/ai_qa/agents/mary.py` — inherited-then-immediate-generate lifecycle; `handle_approve` advances `current_review_index` **positionally** and transitions to `DONE` at `current_review_index >= len(self.test_cases)` ([mary.py:138-161](src/ai_qa/agents/mary.py:138)); `_write_approved_test_cases` saves with the **hardcoded** `confidence:1.0`/`source_url:""` side-car ([mary.py:285-305](src/ai_qa/agents/mary.py:285)); no `self.phase`, no `self.confirmed_requirements`, no `self._reviewed_indices`.
- `src/ai_qa/models.py` — `TestCase` ([:265-298](src/ai_qa/models.py:265)) has only `title`/`preconditions`/`steps`/`expected_results`/`automation_hints`/`tags` + the `filename` property. **No** `source_requirement_id`/`source_url` (12.2), **no** `confidence`/`confidence_level`/`confidence_rationale` (12.3), **no** `approved_by`/`approved_at` (12.4).

12.5 reads metadata fields that **only exist after 12.2/12.3/12.4 land**. Specifically 12.5 assumes:

1. **From 12.2:** `TestCase.source_requirement_id`, `source_requirement_name`, `source_url`, `feature_area`, `warnings` — the source attribution this story lifts into save metadata.
2. **From 12.3:** `TestCase.confidence` (`float | None`), `confidence_level` (`ConfidenceLevel | None`), `confidence_rationale` (`list[str]`) — the confidence data this story lifts into save metadata (and the real value that replaces the `1.0` hardcode).
3. **From 12.4:** `TestCase.approved_by` / `approved_at` (the approval stamp), **and** 12.4's reshaped `handle_approve` (index-addressable, `_reviewed_indices`-keyed `DONE` gate). 12.5's AC3 hardening hooks into **that** `DONE` branch.

**If 12.1–12.4 are not all merged when you start, STOP and flag it** — do not re-implement them here, and do not lift fields that don't exist yet. 12.5 **extends** the 12.4 versions of `handle_approve` / `_write_approved_test_cases` and reads the 12.2/12.3/12.4 `TestCase` fields; it does not re-create them. Reconcile against live code and note any divergence in Completion Notes (per [verify-subagent-claims](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/verify-subagent-claims.md) and [create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md)).

---

## Tasks / Subtasks

- [x] **Task 1 — Adapter: idempotent-by-name `save_test_case` (AC3)**
  - [x] In [src/ai_qa/pipelines/artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py), rewrite `save_test_case` ([:134-137](src/ai_qa/pipelines/artifact_adapter.py:134)) to mirror `save_requirement`'s D8 idempotent pattern ([:51-103](src/ai_qa/pipelines/artifact_adapter.py:51)): snapshot prior `kind="testcase"` rows with the **same name** BEFORE saving; save the new copy first (the per-artifact write is atomic); only after the new row commits, best-effort `delete_artifact` the superseded prior rows (log-and-continue on delete failure). Keep the `_schedule_change_event(artifact.id, "created")` broadcast. This guarantees a retry after a partial failure converges to exactly one artifact per test-case name instead of duplicating.
  - [x] **(Saved Question #1 — recommended default: YES)** Extend the signature to accept optional provenance so the generic 11.7 columns are queryable on the test-case row without parsing the JSON: `save_test_case(self, name, test_case, *, source_type=None, source_url=None, warnings=None)`. Pass them through to `save_artifact(...)` (which already accepts them — [service.py:84-86](src/ai_qa/artifacts/service.py:84)) instead of via `_save_text`. Default `None` keeps every existing caller valid. If Thuong prefers side-car+content-only, skip this sub-task and leave `save_test_case` calling `_save_text`.

- [x] **Task 2 — Agent: real side-car metadata + failure-safe batch save (AC1, AC3)**
  - [x] In [src/ai_qa/agents/mary.py](src/ai_qa/agents/mary.py), rewrite `_write_approved_test_cases` ([:285-305](src/ai_qa/agents/mary.py:285)) to **return `bool`** (`True` = every test case saved; `False` = at least one failed and the batch was rolled back) and to build the side-car from the **real** `TestCase` fields. Replace the hardcoded `source_url:""`/`confidence:1.0` body with (narrow `self.project_context is not None` first — Pyrefly):

    ```python
    async def _write_approved_test_cases(self) -> bool:
        """Persist all approved test cases. All-or-nothing within the batch (AC3)."""
        if self.project_context is None:
            raise ValueError("MaryAgent requires an active project context.")
        adapter = PipelineArtifactAdapter(self.project_context)
        saved_ids: list[UUID] = []
        try:
            for tc in self.test_cases:
                artifact = adapter.save_test_case(
                    f"{tc.filename}.json",
                    tc.model_dump_json(indent=2),
                    source_type=tc.source_type,          # Saved Q#1 columns (omit if sidecar-only)
                    source_url=tc.source_url,
                    warnings=[{"message": w} for w in tc.warnings] or None,
                )
                saved_ids.append(artifact.id)
                adapter.save_metadata(
                    f"{tc.filename}.metadata.json",
                    {
                        "source_requirement_id": tc.source_requirement_id,
                        "source_requirement_name": tc.source_requirement_name,
                        "source_url": tc.source_url or "",
                        "confidence": tc.confidence,
                        "confidence_level": tc.confidence_level,
                        "confidence_rationale": tc.confidence_rationale,
                        "approved_by": tc.approved_by,
                        "approved_at": tc.approved_at,
                        "model": self.config.model_name,
                        "test_case_title": tc.title,
                    },
                )
            return True
        except Exception as exc:
            logger.error("Failed to save approved test cases: %s", exc, exc_info=True)
            # AC3: all-or-nothing — remove anything saved in THIS batch so no partial
            # set is left available to Sarah. delete is best-effort; save_test_case is
            # idempotent-by-name so a retry still converges if a rollback delete fails.
            for artifact_id in saved_ids:
                try:
                    self.project_context.artifact_service.delete_artifact(
                        project_id=self.project_context.project_id, artifact_id=artifact_id
                    )
                except Exception:
                    logger.warning("Rollback delete failed for test case artifact %s", artifact_id)
            return False
    ```

    Notes: narrow `artifact_service`/`project_id` (both `… | None`) before the rollback `delete_artifact` (Pyrefly — see project-context "Narrow Optional before use"). Import `from uuid import UUID` if not already imported. The `confidence`/`confidence_level` may legitimately be `None`/`"low"` — store them verbatim (no `1.0` fallback). Replace the stale docstring "...or workspace/testcases/" — Mary saves only via the artifact service.
  - [x] If Thuong chooses side-car-only (Saved Q#1 = NO), drop the three `source_type`/`source_url`/`warnings` kwargs from the `save_test_case` call (the metadata still lives in the side-car + the JSON content).

- [x] **Task 3 — Agent: gate DONE on save success + AC3 recovery message (AC3)**
  - [x] In `MaryAgent.handle_approve` (the **12.4** index-addressable `DONE` branch — on the live pre-12.4 baseline it is [mary.py:146-157](src/ai_qa/agents/mary.py:146)), replace the unconditional `await self._write_approved_test_cases()` → `transition_to(DONE)` → success message with a save-result check:

    ```python
    saved_ok = await self._write_approved_test_cases()
    if not saved_ok:
        # AC3: do NOT mark approved/available; stay reviewable so re-approve retries.
        await self.send_message(
            self._format_error_message(
                [
                    "Failed to save the approved test cases to the project artifact store.",
                    "No partial test cases were left saved.",
                    "Please approve again to retry the save.",
                ]
            ),
            message_type="error",
        )
        await self.transition_to(AgentState.REVIEW_REQUEST)
        await self._present_current_test_case()
        return  # do NOT transition to DONE; do NOT send the success message
    await self.transition_to(AgentState.DONE)
    await self.send_message(
        f"{len(self.test_cases)} test cases saved to project artifacts",
        message_type="success",
    )
    ```

    > Snippet-fidelity note ([create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md)): this **replaces only the save→DONE→success body** inside 12.4's "all cases reviewed → finalize" branch. **Preserve** 12.4's surrounding structure verbatim — the `_reviewed_indices` bookkeeping, the index-addressable approve, and the low-confidence defensive guard (12.3) that runs **before** finalize. The AC3 early-`return` must keep the workflow at `REVIEW_REQUEST` (re-presenting a case) so the next `approve` re-enters the finalize branch and retries the (now idempotent) save. On the **pre-12.4 positional baseline**, apply the same check around [mary.py:147-157](src/ai_qa/agents/mary.py:147) and on failure `return` **without** advancing past the last index (so re-approve retries) — flag the divergence in Completion Notes.
  - [x] `_format_error_message` is on `BaseAgent` ([base.py](src/ai_qa/agents/base.py)) — confirm it is reachable from Mary (Bob uses it for the 11.7 save-failure message). No new import expected.

- [x] **Task 4 — Backend tests: AC1 metadata + AC3 hardening (AC1, AC3)**
  - [x] **AC1 — real side-car metadata.** Added `test_write_approved_uses_real_sidecar_metadata` in `tests/test_agents/test_mary.py` (class `TestMaryArtifactSave125`). Asserts real values (not `1.0` hardcode) for confidence, source_url, approved_by, etc.
  - [x] **AC3 — save failure keeps reviewable, no DONE, no success, no partial set.** Added `test_save_failure_no_done_error_message_rollback` — failure on 2nd save, asserts no DONE, error message, `delete_artifact` called for first artifact id, REVIEW_REQUEST reached.
  - [x] **AC3 — idempotent retry convergence** Added `test_save_test_case_idempotent_by_name` in `tests/pipelines/test_pipeline_artifact_adapter.py` with real SQLite. Same-name re-save yields exactly one row.
  - [x] **Regression:** `test_handle_approve_transitions_to_done_when_all_approved` and `test_handle_approve_writes_approved_test_cases` still pass. Full 1243-test suite green.
  - [x] Run the **whole** suite with `--no-cov` — 1243 passed.

- [x] **Task 5 — Backend test: AC2 query reachability (no workspace path) (AC2)**
  - [x] Added `test_save_test_case_ac2_query_reachability` in `tests/pipelines/test_pipeline_artifact_adapter.py`. Asserts `load_test_cases()` returns the artifact, storage_path starts with `projects/{project_id}/test_cases/`, no `workspace/` in path, other project returns `[]`.

- [x] **Task 6 — Verify (no migration; backend-only)**
  - [x] Backend: `uv run pytest --no-cov` — 1243 passed. `uv run mypy src` — clean (79 source files, 0 issues).
  - [x] Frontend: `npm run typecheck` — clean (no FE change). `npm run lint` — clean. `npm run test` — all pass.
  - [x] Confirmed **no Alembic migration** required: `kind="testcase"` → `test_cases/` mapping already exists in `storage.py:32-33`; 11.7 provenance columns (`source_type`, `source_url`, `warnings`) already exist on `Artifact` table; `TestCase` is a Pydantic model serialized to JSON content, not a DB table.

---

## Dev Notes

### Build-order reality — what's on disk vs. what this story assumes

On the `b4ce65f` baseline (with Epic 11 uncommitted in the working tree), **none of 12.1–12.4 are merged**. The current [mary.py](src/ai_qa/agents/mary.py) `_write_approved_test_cases` ([:285-305](src/ai_qa/agents/mary.py:285)) hardcodes `confidence:1.0`/`source_url:""` and the current `TestCase` ([models.py:265-298](src/ai_qa/models.py:265)) has none of the source/confidence/approval fields. The natural build order is **12.1 → 12.2 → 12.3 → 12.4 → 12.5**, so by the time 12.5 is implemented:

- 12.4 will have reshaped `handle_approve` to the index-addressable `_reviewed_indices` model and added `TestCase.approved_by`/`approved_at`. Task 3 modifies **that** finalize branch; Task 2 reads `tc.approved_by`/`approved_at`.
- 12.3 will have added the confidence triple + the deterministic engine. Task 2 reads `tc.confidence`/`confidence_level`/`confidence_rationale` (replacing the `1.0` hardcode).
- 12.2 will have added the source attribution fields + per-case `warnings`. Task 2 reads `tc.source_requirement_id`/`source_requirement_name`/`source_url`.

If a dependency is unmerged, **stop and flag** — do not lift fields that don't exist. Treat any divergence (12.4's exact finalize-branch variable names, the `_reviewed_indices` shape) as a flag-during-dev item, not a guess.

### AC1 — the metadata fields, and where each lives

| AC1 field | Where it is stored | Source |
| --- | --- | --- |
| creator | `artifacts.created_by_user_id` (native) | `context.user_id` via `save_test_case` → `save_artifact(owner_user_id=...)` |
| updater | `artifacts.updated_by_user_id` (native) | same |
| originating thread | `artifacts.thread_id` (native) | `context.thread_id` |
| originating agent run | `artifacts.agent_run_id` (native) | `context.agent_run_id` |
| timestamp | `artifacts.created_at` / `updated_at` (native, `TimestampMixin`) | DB default |
| artifact kind | `artifacts.kind = "testcase"` (native) | `save_test_case` |
| **source requirement artifact id** | **test-case JSON content** (`source_requirement_id`) **+ side-car** (+ optional `source_url` column, Saved Q#1) | `TestCase.source_requirement_id` (12.2) |
| **confidence data** | **test-case JSON content** (`confidence`/`confidence_level`/`confidence_rationale`) **+ side-car** | `TestCase.confidence*` (12.3) — **replaces the `1.0` hardcode** |
| **approval status** | **test-case JSON content** (`approved_by`/`approved_at`) **+ side-car** | `TestCase.approved_by`/`approved_at` (12.4) |

So 12.5 adds **no DB column** — the native columns cover 6 fields, and the three test-case-specific fields are durably persisted in the `model_dump_json` content (and surfaced in the expanded side-car). This mirrors 11.7's relationship (native columns + content + audit side-car); the difference is 11.7 *also* promoted requirement provenance to first-class columns because **Mary** needed to query it — for test cases, **Sarah/13.1** can read it from the test-case JSON it loads, so columns are optional (Saved Question #1).

### AC2 — query reachability, and why "only approved" is automatic

AC2 requires saved test cases to be reachable through **project-scoped artifact queries** with **no workspace path**, returning **only approved** test cases. That surface already exists and needs no new endpoint:

- Backend: `ArtifactService.list_artifacts(project_id, kind="testcase")` + `read_current_content(artifact)`; `PipelineArtifactAdapter.load_test_cases()` ([artifact_adapter.py:139-141](src/ai_qa/pipelines/artifact_adapter.py:139)) wraps it. Storage reads go through `ArtifactStorage` keyed by `storage_path` — never a raw `workspace/` path.
- API: `GET /projects/{id}/artifacts?kind=testcase`, `/tree` (the `test_cases` folder), `/{artifact_id}`, `/{artifact_id}/content`.

**"Only approved" is structural, not filtered.** Unlike requirements — which have a pre-approval **draft** (`{page_id}.md`, provenance NULL) and an approved copy (`{page_id}/requirement.md`, provenance set), discriminated by `source_type IS NOT NULL` ([12.1 Dev Notes](_bmad-output/implementation-artifacts/12-1-test-case-generation-input-selection.md)) — **there is no draft test case.** `_write_approved_test_cases` runs **only** at `DONE`, after every case has been approved through the per-item review loop. So every `kind="testcase"` artifact is approved by construction; 13.1 can `list_artifacts(kind="testcase")` directly with **no** discriminator. (If a future story ever adds a pre-approval draft test case, it must introduce a discriminator the way requirements did — note this for 13.1, but do not build it here.)

### AC3 — what "no partial output" means here, and the layered failure handling

There are **two** atomicity layers, plus a convergence guarantee:

1. **Per-artifact atomicity (existing).** `ArtifactService.save_artifact` flushes the row, writes storage, appends the version, commits; on **any** exception it rolls back the DB and deletes the just-written storage object ([service.py:132-137](src/ai_qa/artifacts/service.py:132)). So a **single** failed `save_test_case` leaves no half-written artifact.
2. **Batch all-or-nothing (new, Task 2).** Mary saves the **whole** approved set in a loop. If case 3 of 5 fails, cases 1–2 are already committed. `_write_approved_test_cases` therefore tracks `saved_ids` and, on failure, best-effort `delete_artifact`s every id saved *in this batch* → no partial set is left in `test_cases/`. Combined with **not** transitioning to `DONE`, Sarah (whose hand-off only happens post-`DONE`) can never consume a partial set.
3. **Idempotent-by-name retry (new, Task 1).** If a rollback delete itself fails, a re-approval re-runs the now-idempotent `save_test_case`, which supersedes any same-named survivor → the set converges to exactly N artifacts with no duplicates. This is the same D8 guarantee `save_requirement` got in 11.8.

The user-facing half of AC3 (Task 3): on failure, a UX-DR12 three-part `error` message + the workflow stays at `REVIEW_REQUEST` (not `DONE`, no `"saved"` success message), so re-approving retries. This mirrors 11.7's Bob save-failure behavior exactly (page stays un-resolved, re-approve retries).

> Edge case to note in the dev record: each test case is **two** saves (`save_test_case` + the side-car `save_metadata`). If the JSON saves but the side-car fails, the batch rollback removes the JSON id too (it's in `saved_ids`) — but only if you append the id **before** the side-car call and let the side-car failure propagate into the same `try`. The snippet in Task 2 does this (append `artifact.id`, then `save_metadata`, both inside the loop's `try`). The side-car is an audit duplicate of the content/columns, so a side-car-only failure rolling back the whole batch is acceptable (re-approval rewrites both).

### Why fix the side-car here (and not in 12.3/12.4)

12.2/12.3/12.4 each explicitly **deferred** the save-metadata expansion to 12.5 and left the `confidence:1.0` hardcode in place ([12.2 scope](_bmad-output/implementation-artifacts/12-2-browser-automation-oriented-test-case-generation.md): "Save metadata stays as-is… that is Story 12.5"; [12.3 Saved Q#3](_bmad-output/implementation-artifacts/12-3-confidence-scoring-for-generated-test-cases.md): "leave it for 12.5"; [12.4 sibling note](_bmad-output/implementation-artifacts/12-4-mary-review-workflow.md): "the `confidence:1.0` sidecar hardcode is still 12.5's to reconcile"). 12.5 is where the real metadata lands because by now all the source/confidence/approval fields exist on the model. Keeping the fix here (not scattered) is why the per-case fields persisted automatically in 12.2–12.4 (via `model_dump_json`) but the **side-car** stayed fake until now.

### Project-context rules that bite here

- **Narrow Optional before use:** `self.project_context`, `context.artifact_service`, `context.project_id` are `… | None`. `assert self.project_context is not None` (already at the top of `_write_approved_test_cases`); narrow `artifact_service`/`project_id` before the rollback `delete_artifact` (Pyrefly `bad-argument-type`). `tc.confidence`/`confidence_level` are `… | None` — store verbatim in the side-car dict (JSON-serializable), never coerce to `1.0`.
- **No redundant cast / conversion:** `model_dump_json(indent=2)` returns `str`; do not wrap. `tc.source_url` is `str | None`; the side-car uses `tc.source_url or ""` (the `or` is needed, not a redundant cast).
- **No bare `except`:** the AC3 catch is `except Exception as exc:` with `logger.error(..., exc_info=True)` then a user-safe retry message — it does **not** re-raise (recovery path). `pytest.raises(Exception)` is prohibited in tests — use a specific `side_effect` type.
- **Security:** the side-car carries only `source_url` (a Confluence/Jira URL), confidence numbers/strings, `approved_by` (email/id), `model` name, title. **Never** put MCP/LLM tokens, raw HTML, or config dicts into the side-car/columns/messages/logs. The leak-canary tests must stay green.
- **JSON column shape (Saved Q#1 only):** if stamping the `warnings` column on the test-case row, store `list[dict[str, Any]]` (e.g. `[{"message": w} for w in tc.warnings]`), never raw strings or model objects — matches the column type and the 11.7 `warnings` shape.
- **`uv` only** for backend; `npm` only in `/frontend`. No `python3`. No `# type: ignore` / `@ts-ignore`.

### Do NOT regress these existing behaviors

- The success path: at `DONE` with all cases approved and saves succeeding, Mary transitions to `DONE` and sends the `"N test cases saved"` success message exactly as before (just now gated on `saved_ok`).
- 12.4's index-addressable approve/reject, the `_reviewed_indices` `DONE` gate, and 12.3's low-confidence defensive guard run **before** the finalize/save and are untouched.
- `save_requirement` / `delete_draft_requirement` / `load_requirement_markdown` (Bob's side) are unchanged. `save_artifact`'s atomic write and `create_version` are unchanged.
- The artifact API responses stay backward-compatible (no new fields beyond 11.7's). Epic-10 artifact-tree behavior is unchanged — see [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md): the artifact path is **sync**; `_schedule_change_event` no-ops outside an event loop (fine for unit tests).

### Testing approach (match the house style)

- **Backend agent:** `@pytest.mark.asyncio`; patch `ai_qa.agents.mary.PipelineArtifactAdapter` at the class boundary; assert on `mock_adapter.save_metadata.call_args_list` (real metadata) and the AC3 `side_effect` path (error message + no `DONE` + no success + rollback `delete_artifact`). Build `self.test_cases` directly with 12.2/12.3/12.4 fields.
- **Adapter / AC2 / idempotency:** use the real `ArtifactService` over in-memory SQLite with project/user fixtures (copy `tests/pipelines/test_pipeline_artifact_adapter.py`); assert `storage_path` is under `projects/{id}/test_cases/`, that `load_test_cases()` round-trips, and that a same-name re-save yields exactly one row.
- **Frontend:** no new component; the change is backend-only — `npm run typecheck`/`lint`/`test` must stay green.
- A full Playwright E2E is **not** required (consistent with prior save stories — reaching `DONE` needs live LLM generation, and LLM-driven generation isn't E2E-reproducible without a provider key; no `page.route` mocking allowed). Backend pytest is the guardrail. If a stub provider is available, an optional E2E can cover the AC3 retry message path; document any deferral in Completion Notes.

### Latest tech / external context

No new external library or version is introduced. All tech is already pinned in [project-context.md](project-context.md): Pydantic `model_dump_json`, SQLAlchemy 2.0 `Session` (sync artifact path), FastAPI response models (unchanged), React 19.2/TS 6 strict (no FE change). No migration, no new package, no web research required.

### Project Structure Notes

**Modified files (backend):**

- `src/ai_qa/pipelines/artifact_adapter.py` — `save_test_case` made idempotent-by-name (+ optional provenance params, Saved Q#1).
- `src/ai_qa/agents/mary.py` — `_write_approved_test_cases` rewritten (real side-car metadata + `bool` return + batch rollback, stale-docstring cleanup); `handle_approve` finalize branch gates `DONE`/success on the save result and adds the AC3 retry path.

**New files:** new/extended tests in `tests/test_agents/test_mary.py` and `tests/pipelines/test_pipeline_artifact_adapter.py`. **No DB migration. No new package. No frontend file.**

### Previous-story intelligence

- **Story 11.7** (`done`) — the **direct analog**: authoritative on-approve save (`save_requirement`), provenance promoted to first-class columns, AC3 hardening via `try/except` + un-resolve + retry message, AC2 query reachability proven, the audit side-car kept. 12.5 follows the same shape for test cases (idempotent save, batch rollback, retry message, query reachability) — the main difference is the **batch** (Mary saves all cases at once) needs all-or-nothing rollback, where Bob saved one page at a time. Reuse `_format_error_message` for the retry message and `delete_artifact` for rollback, exactly as 11.7 did.
- **Story 11.8 / D8** (`done`) — made `save_requirement` idempotent-by-name (save-new-first-then-delete-old, to preserve AC3 "no zero-row window"). Task 1 copies this pattern into `save_test_case`.
- **Story 12.4** (`ready-for-dev`) — adds `approved_by`/`approved_at` and the index-addressable `handle_approve`/`_reviewed_indices` `DONE` gate. 12.5 lifts the approval stamp into save metadata and hooks AC3 into the 12.4 finalize branch.
- **Story 12.3** (`ready-for-dev`) — adds the confidence triple; flagged the `confidence:1.0` hardcode as 12.5's to reconcile (Saved Q#3). 12.5 stores the real confidence.
- **Story 12.2** (`ready-for-dev`) — adds `source_requirement_id`/`name`/`source_url`; flagged `source_requirement_id` as "the hook 12.5 will lift into save metadata."
- **Story 13.1 (Sarah)** (`backlog`) — the consumer: "load approved test cases, prioritize originating thread, user confirms/adjusts." It is the analog of 12.1 and will add `load_approved_test_cases` to the adapter + a Sarah input-selection panel. 12.5 must keep the test-case content + query surface complete so 13.1 only **lifts**, not re-derives. Keep `save_test_case`/`load_test_cases` generic so the 12.1 loader pattern reapplies.
- **Epic 10** (`done`) — `ArtifactService`/`PipelineArtifactAdapter`/storage keys/`save_artifact` atomicity/artifact API/realtime change events. 12.5 extends none of the sync path; it reuses `delete_artifact` + the atomic `save_artifact`.

### Git intelligence (recent work patterns)

Recent commits (`b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`, `9d878c5 feat(api): emit project-scoped artifact change events`) center on Epic 10 artifact events. **Epic 11 is uncommitted in the working tree (incl. the `c8e6ace95b08` provenance migration, `save_requirement`/`delete_draft_requirement`); Stories 12.1–12.4 are NOT yet implemented** — verify they are present before relying on the 12.2/12.3/12.4 `TestCase` fields and 12.4's finalize branch. The established pattern (followed by 11.7/11.8): artifact metadata in PostgreSQL + bytes in storage, idempotent-by-name saves, atomic `save_artifact` with a fire-and-forget change event, `delete_artifact` for dedupe/rollback. 12.5 follows it exactly.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1231-1251] — Story 12.5 ACs (save under `projects/{project_id}/test_cases/`; metadata list incl. source IDs/confidence/approval/creator/updater/thread/agent-run/timestamp; project-scoped approved-only queries; save-failure recovery); Epic 12 FRs FR5/FR22/FR27 (1141)
- [Source: _bmad-output/planning-artifacts/architecture.md:818-822] — Mary flow: read requirements via artifact service → extractor → `artifacts/service.py` → `projects/{project_id}/test_cases/`
- [Source: _bmad-output/planning-artifacts/architecture.md:280,336-360] — project-scoped artifact folders + Artifact metadata field list (creator/updater, thread, agent_run, timestamps, non-secret execution metadata)
- [Source: _bmad-output/planning-artifacts/architecture.md:518,533] — agents never read/write storage directly (always via artifact service)
- [Source: src/ai_qa/agents/mary.py:285-305] — `_write_approved_test_cases` (rewrite: real metadata + failure-safe); :138-161 `handle_approve` finalize branch (gate DONE on save); :300 hardcoded `confidence:1.0`; :51-52 `__init__` state
- [Source: src/ai_qa/pipelines/artifact_adapter.py:134-137] — `save_test_case` (make idempotent); :51-103 `save_requirement` (D8 idempotent reference); :105-128 `delete_draft_requirement`; :139-141 `load_test_cases` (AC2 seam); :151-157 `save_metadata`; :191-202 `_save_text`; :234-246 `_load_text_artifacts`/`_to_pipeline_artifact`
- [Source: src/ai_qa/artifacts/storage.py:32-33] — `build_artifact_key` `kind="testcase"` → `test_cases/` (AC1 path already correct); :55-56 `folder_for_kind`
- [Source: src/ai_qa/artifacts/service.py:74-140] — `save_artifact` atomic write (rollback + storage delete on exception) + already accepts `source_type`/`source_url`/`warnings`; `delete_artifact` (rollback/dedupe)
- [Source: src/ai_qa/models.py:265-298] — `TestCase` (read source/confidence/approval fields after 12.2–12.4; `filename` property at :291-298); `TestCaseStep` (244-262)
- [Source: src/ai_qa/agents/base.py] — `_format_error_message` (UX-DR12 retry message); lifecycle (`handle_approve`/`handle_reject`/`transition_to`)
- [Source: src/ai_qa/pipelines/context.py] — `PipelineContext` provenance fields
- [Source: src/ai_qa/api/artifacts.py] — `ArtifactResponse`/detail/tree already expose `source_type`/`source_url`/`warnings` (11.7) — test-case rows ride the same response (no API change)
- [Source: tests/test_agents/test_mary.py:271-289] — existing `handle_approve` save test (extend for AC1/AC3); :233-289 approve scaffold
- [Source: tests/pipelines/test_pipeline_artifact_adapter.py] + [tests/unit/test_artifact_service_provenance.py] — real-service in-memory SQLite scaffold (AC2 + idempotency)
- [Source: _bmad-output/implementation-artifacts/11-7-requirements-artifact-save.md] — the analog save story (idempotency, AC3 hardening, query reachability, audit side-car)
- [Source: _bmad-output/implementation-artifacts/12-2/12-3/12-4-*.md] — the model fields + finalize branch this story lifts/hooks into
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional, no redundant cast); no bare except; no `# type: ignore`; security (no secret/HTML/config in fields/logs)

### Definition of Done

- [ ] Approved test cases are saved under `projects/{project_id}/test_cases/` (existing `kind="testcase"` mapping) with a side-car carrying **real** `source_requirement_id`/`source_requirement_name`/`source_url`, `confidence`/`confidence_level`/`confidence_rationale`, `approved_by`/`approved_at`, `model`, `test_case_title` — the `confidence:1.0`/`source_url:""` hardcodes are gone; native columns cover creator/updater/thread/agent-run/timestamp (AC1).
- [ ] `save_test_case` is idempotent-by-name (a same-name re-save yields exactly one row); `_write_approved_test_cases` returns `bool` and rolls back the whole batch on any failure (no partial set in `test_cases/`) (AC3).
- [ ] On save failure, `handle_approve` sends a UX-DR12 retry message, does **not** transition to `DONE`, does **not** send the success message, and leaves the workflow reviewable so re-approval retries; on success it transitions to `DONE` + success message exactly as before (AC3).
- [ ] Saved test cases are reachable via `load_test_cases()` / `list_artifacts(kind="testcase")` / the artifact API, project-scoped, **no** workspace-path read; only approved test cases exist (no draft) (AC2); the seam Sarah/13.1 will consume is proven by a test.
- [ ] No Alembic migration (confirmed); no new frontend component; `TestCase` TS interface unchanged (12.4 already synced it).
- [ ] Existing Mary success-path tests pass (updated to the 12.4 shape); the save path opens no MCP client and calls no LLM; leak-canary tests green.
- [ ] New tests: AC1 real-metadata side-car, AC3 failure-keeps-reviewable + no-DONE + batch-rollback, idempotent-retry convergence, AC2 query reachability.
- [ ] `uv run pytest --no-cov` green; `uv run mypy src` clean (Pyrefly-clean); `npm run lint`/`typecheck`/`test` green in `/frontend`.

---

## Saved Questions (for Thuong — confirm or correct)

1. **First-class queryable columns on the test-case row, or side-car + content only?** Default = **stamp the generic 11.7 columns** (`source_url` from the source requirement, `warnings` from the per-case ambiguity warnings) on the test-case artifact via an extended `save_test_case`, so the artifact API/tree exposes them and Sarah/13.1 can query without parsing the JSON — **no migration** (columns already exist). Alternative = side-car + JSON-content only (simpler; Sarah reads the test-case JSON it already loads). The source-requirement-id / confidence-triple / approval-stamp live in the content + side-car either way (no test-case-specific column is proposed). OK to stamp the generic columns?
2. **AC3 partial-failure semantics.** Default = **all-or-nothing within a batch** (on any failure, best-effort delete every artifact saved in this batch so no partial set is left) **+ idempotent-by-name retry** (so a retry converges with no duplicates even if a rollback delete fails). Alternative = rely on idempotent-retry **only** (don't delete the partial set; not-`DONE` keeps it from Sarah, and a retry overwrites) — simpler, but a partial set technically sits in `test_cases/` until the user retries or abandons. Go all-or-nothing?
3. **Retry affordance after save failure.** Default = re-present the current test case at `REVIEW_REQUEST` so the next **approve** re-runs the (idempotent) save. Alternative = a dedicated "Retry save" action/message. Keep the re-approve-to-retry default (mirrors 11.7's re-approve-to-retry)?
4. **Test-case E2E coverage.** Default = backend pytest is the guardrail; **no** Playwright E2E for the save (reaching `DONE` needs live LLM generation, which isn't E2E-reproducible without a provider key; `page.route` mocking is forbidden). Acceptable, or attempt an E2E against a stub provider if one is available in the E2E env?

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- **No Alembic migration required.** `kind="testcase"` → `projects/{project_id}/test_cases/` storage mapping already exists (`storage.py:32-33`). The 11.7 provenance columns (`source_type`, `source_url`, `warnings`) already exist on the `Artifact` table. `TestCase` is a Pydantic model serialized to JSON content (not a DB table), so all 12.2/12.3/12.4 fields persist automatically via `model_dump_json`.
- **12.1–12.4 were already merged** in the working tree at the time of implementation. `TestCase` already had all source/confidence/approval fields; `handle_approve` already had the 12.4 index-addressable `_reviewed_indices` model. Story 12.5 extended what was there.
- **Task 2 divergence note:** Snippet in the story referenced `tc.source_type` but `TestCase` has no `source_type` field (it's a generated artifact, not sourced from Confluence/Jira). Implemented without `source_type` — only `source_url` and `warnings` are passed to `save_test_case`. The default `source_type=None` keeps the column `NULL` on test-case rows, which is correct.
- **AC3 retry pattern:** On save failure, `handle_approve` stays at `REVIEW_REQUEST` and re-presents the full list. Re-approving the final index re-triggers the finalize branch and retries the (now idempotent-by-name) save, exactly mirroring the 11.7 Bob re-approve-to-retry pattern.
- **AC2 "only approved" is structural:** No discriminator column needed. `_write_approved_test_cases` runs only at DONE (after per-item review loop), so every `kind="testcase"` artifact is approved by construction. Noted in the AC2 test and in the test comments for Story 13.1.
- **Edge case (side-car failure):** `saved_ids.append(artifact.id)` precedes `save_metadata(...)` in the loop body. If the side-car save fails, the JSON artifact id is already in `saved_ids` and will be rolled back — correct all-or-nothing semantics.
- **Full suite:** 1243 backend tests passed, 0 failures. `uv run mypy src` clean (79 files). Frontend: 196 unit tests passed, lint clean, typecheck clean.

### File List

- `src/ai_qa/agents/mary.py` — `_write_approved_test_cases` rewritten (returns `bool`, real sidecar metadata, all-or-nothing batch rollback); `handle_approve` DONE branch gated on save result + AC3 retry path; `from uuid import UUID` import added
- `src/ai_qa/pipelines/artifact_adapter.py` — `save_test_case` made idempotent-by-name (D8 pattern mirroring `save_requirement`); optional `source_type`/`source_url`/`warnings` provenance params added
- `tests/test_agents/test_mary.py` — `TestMaryArtifactSave125` class added: AC1 real-metadata test, AC3 failure-keeps-reviewable test, success-path regression test
- `tests/pipelines/test_pipeline_artifact_adapter.py` — `test_save_test_case_idempotent_by_name` (AC3 idempotency) and `test_save_test_case_ac2_query_reachability` (AC2 seam) added; `_make_test_db_session` helper added
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — story status updated
