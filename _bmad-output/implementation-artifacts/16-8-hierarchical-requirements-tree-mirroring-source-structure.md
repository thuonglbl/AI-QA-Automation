---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.8: Hierarchical Requirements Tree Mirroring Source Structure

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend + frontend. Today the requirements tree flattens because only the **immediate** parent is captured (`parent_source_id`) and `buildResultTree` orphans any node whose intermediate ancestor isn't in the result set. This story captures + persists the **full ancestor chain** and reconstructs the multi-level tree from it. Decision needed: see "Open question — schema approach".

## Story

As a QA user,
I want the Requirements artifact tree to mirror the multi-level Confluence page hierarchy,
so that I can navigate generated requirements with the same parent/child structure as the source space.

## Acceptance Criteria

1. **Full ancestor chain recorded.** Given a Confluence space whose pages form a multi-level tree (parent pages with nested children across several depths), when Bob saves the extracted requirements artifacts, then each requirements artifact records its full ancestor chain (not only its immediate parent) so the complete source hierarchy is reconstructable.

2. **Tree renders the same nested levels.** Given the Requirements sidebar renders the saved requirements, when the result tree is built, then it displays the same nested levels as the source space — parent nodes contain their child pages at the correct depth — instead of a single flat list.

3. **Robust fallback for missing/incomplete chains.** Given a page has no resolvable parent or an incomplete ancestor chain, when the tree is rendered, then the node falls back to the root level (or nearest known ancestor) and remains visible and distinct rather than being dropped or duplicated.

4. **Predictable, non-destructive expand/collapse + selection.** Given a parent node has child requirements, when the user expands, collapses, or selects nodes, then expand/collapse state and selection behave predictably and do not reset chat input or scroll position.

## Tasks / Subtasks

- [x] **Task 0 — Schema approach DECIDED (AC: 1)**
  - [x] **Approach (A) — persist the full ancestor chain on the artifact** (new nullable column + migration mirroring `7c2f9a3b1e84`/`c98f775f0b00`). Approved by Thuong 2026-06-22. (Approach (B) FE-only reconstruction is rejected — it cannot satisfy AC1/AC3 when an intermediate page is filtered out of the result set, which is the current bug.)

- [x] **Task 1 — Capture the full ancestor chain at read time (AC: 1)**
  - [x] `_extract_parent_id` keeps only `ancestors[-1]` (the immediate parent) and discards the rest ([src/ai_qa/pipelines/confluence_reader.py:26](src/ai_qa/pipelines/confluence_reader.py:26)). Add extraction of the FULL ordered ancestor id list from the Confluence `ancestors` array (root → immediate parent), with the existing `parentId`/`parent`/root fallbacks for the immediate parent.
  - [x] Carry the chain on `PageSummary` (add an `ancestor_ids: list[str]` field next to `parent_id`) ([src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py)).
  - [x] NOTE the MCP caveat: `confluence_search` does not accept an `expand` param, so some responses omit `ancestors` ([confluence_reader.py:736](src/ai_qa/pipelines/confluence_reader.py:736)). When the chain is absent, fall back to the single immediate parent (AC3 handles partial chains). Document this limit.

- [x] **Task 2 — Persist the chain on the artifact (AC: 1)**
  - [x] Add a nullable `ancestor_source_ids` column to `Artifact` (JSON/text list, mirroring how `parent_source_id` was added) ([src/ai_qa/db/models.py](src/ai_qa/db/models.py), Artifact ~line 227). Keep `parent_source_id` for back-compat.
  - [x] New Alembic migration (mirror `alembic/versions/7c2f9a3b1e84_*.py` and the `c98f775f0b00` server_default backfill pattern). Nullable, no backfill required (AC5 of the source story: pre-existing rows stay readable).
  - [x] Stamp the chain on approve in Bob's auto-save where `parent_source_id` is set today ([src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py) `_auto_save_requirements`, ~line 1269). Jira stays `None` (non-hierarchical).
  - [x] Expose the chain on `ArtifactResponse`/`ArtifactTreeEntry` ([src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py)) and the tree endpoint.

- [x] **Task 3 — Reconstruct the multi-level tree on the FE (AC: 2, 3, 4)**
  - [x] Update the TS `Artifact` interface (add `ancestor_source_ids?: string[] | null`) in [frontend/src/components/conversations/ProjectSidebar.tsx](frontend/src/components/conversations/ProjectSidebar.tsx).
  - [x] Update `buildResultTree` to nest using the full ancestor chain: when an intermediate ancestor is NOT in the result set, attach the node to the nearest **present** ancestor (or root) instead of orphaning it to depth 0 — preserving correct relative depth (AC3). Keep the cycle guard + dedup (draft vs approved) + stable sort.
  - [x] Verify expand/collapse (`collapsedNodes` keyed by artifact id) and selection do not reset chat input/scroll (AC4).

- [x] **Task 4 — Tests (all ACs)**
  - [x] Backend: extend `tests/pipelines/test_confluence_reader.py` for full-chain extraction (multi-level ancestors) + partial/absent chain fallback; add an artifact round-trip test for the new column ([tests/unit/test_artifact_service_provenance.py](tests/unit/test_artifact_service_provenance.py) pattern); extend `tests/test_agents/test_bob.py` to assert the chain is stamped on save.
  - [x] Frontend: extend `ProjectSidebar.helpers.test.ts` for a 3+ level tree where an intermediate ancestor is missing (must attach to nearest present ancestor at correct depth, not flatten) + cycle/dedup preserved.
  - [x] Backend: `uv run alembic upgrade head` then `uv run pytest` (whole suite or `--no-cov`). FE: `npm run typecheck` + `npm test`.

## Dev Notes

### Root cause (verified against live code)

- `_extract_parent_id` reads the Confluence `ancestors` list but returns only `ancestors[-1]` — the immediate parent — then falls back to `parentId`/`parent`/root ([confluence_reader.py:26-45](src/ai_qa/pipelines/confluence_reader.py:26)). The deeper chain is available (when the response includes it) but discarded.
- `PageSummary.parent_id` is a single string; there is no chain field ([pipelines/models.py](src/ai_qa/pipelines/models.py)).
- Bob stamps only `parent_source_id` on the artifact ([bob.py](src/ai_qa/agents/bob.py) `_auto_save_requirements`).
- `Artifact` has `title` + `parent_source_id` only (migration `7c2f9a3b1e84`); no ancestor-chain/depth/path column.
- `buildResultTree` nests by matching `parent_source_id` to another artifact **present in the set**; if the intermediate page was filtered (e.g. empty content), the descendant's parent isn't found and it becomes a depth-0 root — the flattening symptom (AC3 target).

### Schema approach — DECIDED (approach A)

**Approved 2026-06-22:** persist the full ancestor chain on the artifact (new nullable column + migration). FE-only reconstruction was rejected because it breaks exactly when an intermediate page is missing from the result set (the current bug). Migrations are pending in this repo — coordinate with [[git-commit-and-branch-preferences]]: Thuong runs `alembic upgrade head` himself.

### Source tree components to touch

- `src/ai_qa/pipelines/confluence_reader.py` — **UPDATE** (`_extract_parent_id` → also emit full chain; or add a sibling extractor).
- `src/ai_qa/pipelines/models.py` — **UPDATE** (`PageSummary.ancestor_ids`).
- `src/ai_qa/db/models.py` — **UPDATE** (`Artifact.ancestor_source_ids`, nullable).
- `alembic/versions/` — **NEW** migration (mirror `7c2f9a3b1e84` + `c98f775f0b00`).
- `src/ai_qa/agents/bob.py` — **UPDATE** (stamp the chain on auto-save; Jira → None).
- `src/ai_qa/api/artifacts.py` — **UPDATE** (`ArtifactResponse`/`ArtifactTreeEntry` + tree endpoint expose the chain).
- `frontend/src/components/conversations/ProjectSidebar.tsx` — **UPDATE** (`Artifact` interface + `buildResultTree`).
- Tests: `tests/pipelines/test_confluence_reader.py`, `tests/unit/test_artifact_service_provenance.py`, `tests/test_agents/test_bob.py`, `frontend/src/components/conversations/ProjectSidebar.helpers.test.ts` — **UPDATE/ADD**.

### Current behavior to PRESERVE (regression guardrails)

- Requirements sidebar shows ONLY final `.md` results; raw companions hidden; friendly name = `title` falling back to page id ([[artifact-ui-storage-overhaul]]).
- Dedup: approved (`{id}/requirement.md`) wins over draft (`{id}.md`) for the same page; cycle guard via `visited`.
- Jira is non-hierarchical → no chain.
- `Artifact.parent_source_id` stays (back-compat); new column is additive + nullable so pre-existing rows render at root (AC3).
- Full-stack sync: backend payload change → TS interface in the same change ([[project-context]]).
- Don't change which artifacts are listed (no raw companions); don't break `data-testid`/`getByText` contracts.

### Testing standards summary

- Backend pytest; SQLite in tests — new nullable column is fine. Round-trip the column via the artifact service provenance test pattern.
- Async SQLAlchemy: eager-load if you query the new field in a serialized path; `.unique()` on joined collections.
- FE: helper unit tests for `buildResultTree` are pure functions — easy to assert depth + attach-to-nearest-ancestor.
- Coverage gate fails on subset runs → whole suite or `--no-cov`.

### Project Structure Notes

- Full-stack: BE schema + pipeline + API + FE tree. One migration. No new dependencies. The chain column is additive; mirrors prior provenance columns.

### References

- Epic + ACs: [epics.md#Story-16.8](_bmad-output/planning-artifacts/epics.md:1848)
- Parent extraction: [confluence_reader.py:26](src/ai_qa/pipelines/confluence_reader.py:26)
- Artifact provenance columns + migration precedent: `alembic/versions/7c2f9a3b1e84_add_title_and_parent_source_id_to_artifacts.py`, `alembic/versions/c98f775f0b00_add_timezone_to_user.py`
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[artifact-ui-storage-overhaul]], [[bob-select-id-handoff]], [16-4](16-4-rich-review-panels.md)

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
