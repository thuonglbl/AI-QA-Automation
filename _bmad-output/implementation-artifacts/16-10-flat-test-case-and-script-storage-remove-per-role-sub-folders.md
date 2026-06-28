---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.10: Flat Test-Case and Script Storage (Remove Per-Role Sub-Folders)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend. Test cases (Mary) and scripts (Sarah) are saved under a per-role sub-folder (e.g. `Admin/login.py`); save them **flat at the folder root** (`login.py`), drop the role-folder segment from both save paths, resolve name-uniqueness across the **whole flat folder**, and keep the role in the MD body header. Good news: **Jack already reads role from sidecar metadata, not the folder path** — minimal downstream change.

## Story

As a QA user,
I want generated test cases and test scripts to be saved at the root of their artifact folder instead of inside a per-role sub-folder,
so that a test case that applies to more than one role is not forced under a single role folder, while the role it belongs to is still visible from the artifact's own content.

## Acceptance Criteria

1. **Test cases saved flat, role kept in body.** Given Mary saves a test case (draft during streaming or approved on confirmation), when the artifact name and storage key are derived, then the test case is stored directly in the Test Cases folder root (e.g. `<case>.md`) with no `<role>/` sub-folder segment, and the role remains recorded in the Markdown body header (the `Role` section).

2. **Scripts (+ sidecar) saved flat.** Given Sarah saves an approved test script, when the script artifact name and storage key are derived, then the script is stored directly in the Test Scripts folder root (e.g. `<script>.py`) with no `<role>/` sub-folder segment, and the script's sidecar metadata file is stored alongside it at the same root level.

3. **Whole-folder name uniqueness.** Given two test cases — or two scripts — normalise to the same base name, when their storage names are computed without a role folder to keep them apart, then name-uniqueness is resolved across the whole flat folder (not per-role), so each artifact maps to a distinct file and none is silently overwritten.

4. **Downstream reads role from content, not path.** Given the role→folder mechanism is no longer used for storage, when the test-case and script save paths are updated, then per-role sub-foldering is removed from both save paths, and any downstream consumer that previously grouped by folder path (e.g. role-aware execution grouping in Jack) reads the role from the artifact content/metadata instead of the folder path.

5. **Back-compat with pre-existing role-foldered artifacts.** Given artifacts already saved under a `<role>/` sub-folder before this change, when the new flat layout is in effect, then the change applies to newly generated artifacts and pre-existing role-foldered artifacts remain readable; regenerating a test case or script saves it at the flat root (no data migration required).

## Tasks / Subtasks

- [ ] **Task 1 — Remove the role folder from Mary's save path; make uniqueness whole-folder (AC: 1, 3)**
  - [ ] In `_persist_test_case`, drop the `role_folder` prefix so the artifact name is `<base>.md` ([src/ai_qa/agents/mary.py](src/ai_qa/agents/mary.py) ~line 1301-1305).
  - [ ] Keep `## Role` in the markdown body (`TestCase.to_markdown` already emits it — [src/ai_qa/models.py](src/ai_qa/models.py) ~line 367). Do NOT drop the role from content.
  - [ ] Resolve base-name collisions across the WHOLE Test Cases folder (not per-role). Today `_unique_artifact_base` dedups within the run batch only; with role folders gone, two roles' same-named cases collide. Extend collision resolution to the flat folder scope (e.g. always disambiguate by `source_requirement_id`/position when the base repeats anywhere in the flat set, and/or check existing artifacts in the folder).

- [ ] **Task 2 — Remove the role folder from Sarah's save path + sidecar; whole-folder uniqueness (AC: 2, 3)**
  - [ ] In `_unique_script_name`, drop the `role_folder` prefix so the script name is `<base>.py` and make the collision check span ALL generated scripts regardless of role (currently keyed per `(role, base_name)`) ([src/ai_qa/agents/sarah.py](src/ai_qa/agents/sarah.py) ~line 1011-1036). Two roles' same-base scripts must now disambiguate (e.g. `<base>__<source_tc_id>.py`).
  - [ ] In `_write_approved_scripts_metadata`, derive the sidecar name from the (now-flat, disambiguated) saved script name so it stays 1:1 and lands at the same root (`<script>.metadata.json`) ([src/ai_qa/agents/sarah.py](src/ai_qa/agents/sarah.py) ~line 1395-1437). Keep `role` inside the sidecar payload.

- [ ] **Task 3 — Confirm Jack reads role from content/metadata, not path (AC: 4)**
  - [ ] Verify Jack's role grouping reads role via `_sidecar_enrichment` → sidecar `role` field, NOT the folder path ([src/ai_qa/agents/jack.py](src/ai_qa/agents/jack.py) `_artifact_role`/`_sidecar_enrichment`/`_confirm_inputs`). Research indicates it already does — so this is a verification + a regression test, not a rewrite.
  - [ ] Confirm Jack's produced-file namespacing (`role_to_folder(role)` prefix on output files) still works from the role read out of metadata, independent of the (now-removed) storage sub-folder.

- [ ] **Task 4 — Remove role-folder usage from the storage paths (AC: 4)**
  - [ ] Confirm `build_artifact_key`/`folder_for_kind` do not themselves inject the role (they don't — the role lives in the artifact NAME passed by Mary/Sarah) ([src/ai_qa/artifacts/storage.py](src/ai_qa/artifacts/storage.py)). `role_to_folder` may remain for Jack's produced-file prefixing; just stop using it in Mary/Sarah save NAMES.

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Update `tests/test_agents/test_mary.py`: replace `test_role_test_case_saved_under_role_subfolder` (asserts `Admin_User/...`) with a flat-root assertion; keep the `## Role` body assertion; add a cross-role same-base uniqueness test.
  - [ ] Update `tests/test_agents/test_sarah.py`: replace `test_role_script_saved_under_role_subfolder` / adjust `test_same_base_different_roles_do_not_collide` → now they DO collide and must disambiguate at the flat root; sidecar name flat + `role` field intact.
  - [ ] `tests/test_agents/test_jack.py`: confirm role grouping still works (reads from sidecar); add a regression that flat-named scripts group by metadata role.
  - [ ] Backend suite green (`uv run pytest`, whole suite or `--no-cov`).

## Dev Notes

### Why this is low-risk on the downstream side

Jack already reads role from the sidecar `role` field via `_sidecar_enrichment`, not the folder path (verified in research). So removing the storage sub-folder does NOT break role-aware execution grouping — it just requires the sidecar to remain 1:1 with the (now-flat, disambiguated) script and to keep its `role` field. The folder segment was only ever cosmetic for the browse UI.

### The real work: collision resolution moves to whole-folder scope

With role folders gone, the per-role disambiguation that kept `Admin/login.py` and `User/login.py` apart collapses to a single `login.py` — a silent overwrite risk (AC3). Move uniqueness to the flat-folder scope:

- Mary: `_unique_artifact_base` currently dedups within the run's `used_names` set only — widen to the whole flat folder (consider existing artifacts, not just this batch).
- Sarah: `_unique_script_name` collision is per `(role, base)` — make it per `base` across all scripts; disambiguate same-base/different-role with the `source_test_case_id` suffix.
- Sidecar must follow the disambiguated name (1:1) so Jack's lookup stays correct.

### Role provenance (unchanged)

Role flows: Mary sets `TestCase.role` (LLM) → `## Role` in markdown (`to_markdown`) → Sarah reads it via `from_markdown` → script sidecar `role` field → Jack reads role from sidecar. The MD body header is the durable record (AC1). Keep all of this.

### Source tree components to touch

- `src/ai_qa/agents/mary.py` — **UPDATE** (`_persist_test_case` drop role folder; `_unique_artifact_base` whole-folder uniqueness). `_role_folder` may be removed if unused after.
- `src/ai_qa/agents/sarah.py` — **UPDATE** (`_unique_script_name` flat + cross-role disambiguation; `_write_approved_scripts_metadata` flat sidecar).
- `src/ai_qa/agents/jack.py` — **READ / VERIFY** (already reads role from sidecar); add regression only.
- `src/ai_qa/artifacts/storage.py` — **READ** (`build_artifact_key`/`folder_for_kind` unchanged; `role_to_folder` kept for Jack produced-file prefix).
- `src/ai_qa/models.py` — **READ** (`TestCase.to_markdown`/`from_markdown` role section unchanged).
- Tests: `tests/test_agents/test_mary.py`, `test_sarah.py`, `test_jack.py` — **UPDATE** assertions.

### Current behavior to PRESERVE (regression guardrails)

- Role stays in the MD body `## Role` section — never drop it (AC1).
- Idempotent save-new-first/delete-old artifact saving; Mary's all-or-nothing approve rollback + orphan draft cleanup.
- Sarah skip-only failure placeholders (`error_message` gate) ([[story-16-12-sarah-auth-bug]]).
- Sidecar stays 1:1 with the script (pairing by name) — must survive flattening.
- Jack per-role session gating + produced-file role namespacing (Slice 6 / Epic 14) — reads role from metadata; keep working.
- Pre-existing role-foldered artifacts remain readable; no data migration (AC5).
- Test cases saved as Markdown ONLY (no JSON sidecar for cases — [[mary-md-testcases-reports-cleanup]]). The Sarah `.metadata.json` sidecar is the script's, not the test case's.

### Testing standards summary

- Backend pytest; the existing role-folder tests are the ones to flip (search `under_role_subfolder`, `do_not_collide`). Add cross-role same-base collision tests at the flat root.
- Coverage gate fails on subset runs → whole suite or `--no-cov`. `uv run` uses py3.14.
- Pyrefly-clean test code (assert optional layers before `.return_value`/`.call_args`).

### Project Structure Notes

- Backend-only; no migration, no schema change, no frontend change (storage NAME changes; the browse UI just shows flat names). No new dependencies.

### References

- Epic + ACs: [epics.md#Story-16.10](_bmad-output/planning-artifacts/epics.md:1900)
- Mary save: [src/ai_qa/agents/mary.py](src/ai_qa/agents/mary.py); Sarah save + sidecar: [src/ai_qa/agents/sarah.py](src/ai_qa/agents/sarah.py); Jack role grouping: [src/ai_qa/agents/jack.py](src/ai_qa/agents/jack.py)
- Storage classifiers: [src/ai_qa/artifacts/storage.py](src/ai_qa/artifacts/storage.py)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[mary-md-testcases-reports-cleanup]], [[epic-14-jack-test-execution]], [[story-16-12-sarah-auth-bug]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
