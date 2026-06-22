---
baseline_commit: 39bec831e2b195b3121a2345a32b282211bd9872
---
# Story 18.3: Downstream Staleness Impact Mapping

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend-led. Given a CHANGED source (from 18.2), walk the artifact lineage to enumerate every generated asset now potentially stale: the requirement artifact(s) from that page/issue → their test cases → their scripts → their execution runs. **The crux of this epic is that artifact→artifact lineage is NOT reliably persisted today** — `Mary`'s test-case → requirement link lives only in-memory + as markdown TEXT (the requirement NAME, not id); `Sarah`'s script → test-case link lives only in a `.metadata.json` sidecar; only `Jack`'s execution → script/test-case link is a real DB FK ([db/models.py:377-382](src/ai_qa/db/models.py:377)). This story makes lineage **explicit and queryable** by adding one self-referential column and populating it at save time, then builds the staleness mapper on top.

## ⚠ DECISION GATE — lineage capture approach (resolve before/at dev start)

The forensic sweep confirmed there is **no artifact→artifact foreign key** in the schema today (verified [db/models.py:227-266](src/ai_qa/db/models.py:227); the only artifact-referencing FKs are `TestExecutionResult.source_script_artifact_id`/`source_test_case_artifact_id`). Two ways to map requirement→test-case→script:

- **Approach A (RECOMMENDED) — add explicit lineage column.** Add ONE nullable self-referential FK `derived_from_artifact_id` (UUID → `artifacts.id`, `ondelete="SET NULL"`) to `Artifact`. Populate it FORWARD at save time: Mary sets it to the requirement artifact id (already in memory as `tc.source_requirement_id`, [test_case_extractor.py:292](src/ai_qa/pipelines/test_case_extractor.py:292) — it is currently DROPPED at save, [mary.py:1306](src/ai_qa/agents/mary.py:1306)); Sarah sets it to the test-case artifact id (already in memory as `GeneratedScript.source_test_case_id`, [sarah.py:50](src/ai_qa/agents/sarah.py:50)). Gives a clean one-column lineage walk, complementing Jack's existing FKs. Robust to the flat-storage change (16.10).
- **Approach B — reconstruct, no schema change.** Walk lineage from existing data: Sarah→test-case via the sidecar `source_test_case_id`; Jack→script/test-case via FKs; BUT Mary→requirement only by **name-matching** the "Source Requirement" text in the test-case markdown against requirement titles. Brittle — breaks when titles collide or 16.10 flattens folders; no migration but unreliable.

**Recommendation: A.** The data already exists in memory at save time and is merely discarded — persisting it is a one-column migration + threading two existing values through two save calls. The ACs/tasks below assume **A**; if Thuong picks B, drop Task 1's migration and replace Task 3's queries with name-match reconstruction (and accept the fragility).

## Story

As a QA user,
I want changed sources mapped to the affected requirements, test cases, scripts, and execution runs via artifact lineage,
so that I can see exactly which generated assets are now potentially stale.

## Acceptance Criteria

1. **Add a persisted lineage link (Approach A).** Given the schema has no artifact→artifact link, when this story is implemented, then `Artifact` gains a nullable self-referential FK `derived_from_artifact_id` (UUID → `artifacts.id`, `ondelete="SET NULL"`, indexed) via an Alembic migration whose `down_revision` is **18.1's `source_snapshots` revision** (NOT the repo head — these two Epic-18 migrations chain). The column is null for sources/requirements (top of the chain) and for legacy rows.

2. **Populate lineage forward — Mary.** Given Mary saves an approved test-case artifact, when she calls `save_test_case` ([mary.py:1306](src/ai_qa/agents/mary.py:1306) → [artifact_adapter.py:142](src/ai_qa/pipelines/artifact_adapter.py:142)), then `derived_from_artifact_id` is set to the originating requirement artifact id — the value already held in memory as `tc.source_requirement_id` ([test_case_extractor.py:292](src/ai_qa/pipelines/test_case_extractor.py:292)), which is presently discarded. Thread it through `save_test_case` → `service.save_artifact` ([service.py:79](src/ai_qa/artifacts/service.py:79)). When `source_requirement_id` is absent (draft/unknown), leave null — never fabricate.

3. **Populate lineage forward — Sarah.** Given Sarah saves a script artifact, when she calls `save_script` ([sarah.py:1123](src/ai_qa/agents/sarah.py:1123) → [artifact_adapter.py:228](src/ai_qa/pipelines/artifact_adapter.py:228)), then `derived_from_artifact_id` is set to the source test-case artifact id (`GeneratedScript.source_test_case_id`, [sarah.py:50](src/ai_qa/agents/sarah.py:50)) — the same value already written to the `.metadata.json` sidecar ([sarah.py:198](src/ai_qa/agents/sarah.py:198)). The sidecar stays (Jack + back-compat read it); the column is the new queryable source of truth.

4. **Map a changed source → its requirement artifacts.** Given a changed Confluence page id / Jira issue key (from 18.2), when the mapper runs, then it finds the requirement artifact(s) derived from that source: `Artifact` rows with `kind="requirements"` AND (`parent_source_id == page_id` OR `name` startswith `{source_id}/` OR `source_url == source_url`) within the project. Confluence requirement artifacts are named `{page_id}/requirement.md` ([artifact_adapter.py:74](src/ai_qa/pipelines/artifact_adapter.py:74)) and carry `parent_source_id`/`source_url`/`source_type` — use those, do not parse markdown.

5. **Walk the lineage down to a staleness set.** Given the affected requirement artifact(s), when the mapper walks down, then it returns the transitive closure of stale assets: requirement(s) → test cases (`Artifact` where `derived_from_artifact_id IN {requirement_ids}`) → scripts (`Artifact` where `derived_from_artifact_id IN {test_case_ids}`) → execution runs (`TestExecutionResult` where `source_script_artifact_id IN {script_ids}` OR `source_test_case_artifact_id IN {test_case_ids}`, [db/models.py:377-382](src/ai_qa/db/models.py:377)). The result is a structured `StalenessImpact { source_id, requirements: [...], test_cases: [...], scripts: [...], execution_runs: [...], unmapped: [...] }`.

6. **Surface "lineage unknown" honestly for legacy assets.** Given a generated artifact created BEFORE this story (so `derived_from_artifact_id` is null), when the mapper cannot link it to a changed source, then it is reported under `unmapped` (or "lineage unknown"), NOT silently dropped and NOT falsely marked stale. The user must be able to tell "this is provably affected" from "we couldn't trace this older asset" ([[verify-subagent-claims]] honesty principle). A best-effort reconstruction for legacy rows (Sarah sidecar `source_test_case_id`; Mary markdown name-match) MAY fill gaps but every reconstructed (vs persisted) link is flagged as lower-confidence.

7. **Mapper is read-only and side-effect-free.** Given the mapper computes a `StalenessImpact`, when it runs, then it performs only SELECTs — it does NOT mark artifacts stale in the DB, delete, or regenerate anything (persisting a stale flag and regenerating are 18.4/18.5 concerns). It returns the impact set for the caller to surface/act on. Async-DB safe: eager-load (`selectinload`/`joinedload`) any relationship it reads; call `.unique()` on joined collections ([[project-context]] SQLAlchemy rules).

## Tasks / Subtasks

- [ ] **Task 1 — `derived_from_artifact_id` column + migration (AC: 1) [Approach A]**
  - [ ] Add `derived_from_artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True, index=True)` to `Artifact` ([db/models.py:227-266](src/ai_qa/db/models.py:227)). Self-referential FK — add an explicit `foreign_keys=`/`remote_side=` only if you also add a relationship; FK-only column is sufficient for the queries here.
  - [ ] `uv run alembic revision --autogenerate -m "add derived_from_artifact_id to artifacts"`. **Set `down_revision` to 18.1's `source_snapshots` revision** (these two Epic-18 migrations form a chain on top of `273b69541e94`). Verify `op.f(...)` self-FK naming + index. Upgrade/downgrade round-trip.
  - [ ] DO NOT confuse with the EXISTING `parent_source_id` (String, the Confluence PARENT PAGE id, [db/models.py:260](src/ai_qa/db/models.py:260)) — that points at a SOURCE page, not an upstream artifact. The new column points at an upstream ARTIFACT. Keep both.

- [ ] **Task 2 — Thread lineage through the save paths (AC: 2, 3)**
  - [ ] `save_artifact` ([service.py:79](src/ai_qa/artifacts/service.py:79)): add a `derived_from_artifact_id: UUID | None = None` kwarg, write it to the row. Add the same kwarg to `PipelineArtifactAdapter.save_test_case` ([artifact_adapter.py:142](src/ai_qa/pipelines/artifact_adapter.py:142)) and `save_script` ([artifact_adapter.py:228](src/ai_qa/pipelines/artifact_adapter.py:228)).
  - [ ] Mary: at the `save_test_case` call ([mary.py:1306](src/ai_qa/agents/mary.py:1306)), pass `derived_from_artifact_id = UUID(tc.source_requirement_id)` when present (it is a str holding an artifact UUID — guard the parse, leave null on failure). NB: `source_requirement_id` is set in [test_case_extractor.py:292](src/ai_qa/pipelines/test_case_extractor.py:292) and survives in memory through to save.
  - [ ] Sarah: at the `save_script` call ([sarah.py:1123](src/ai_qa/agents/sarah.py:1123)), pass `derived_from_artifact_id = UUID(current_script.source_test_case_id)` when present (same guard). Keep writing the sidecar ([sarah.py:198](src/ai_qa/agents/sarah.py:198)) for Jack/back-compat.

- [ ] **Task 3 — `StalenessMapper` (AC: 4, 5, 6, 7)**
  - [ ] New `src/ai_qa/sources/staleness.py` (or beside the snapshot service): `map_impact(*, project_id, source_type, source_id, source_url) -> StalenessImpact`.
  - [ ] Step 1 (AC4): find requirement artifacts for the source via `parent_source_id`/`name` prefix/`source_url` (kind=`requirements`).
  - [ ] Step 2 (AC5): BFS down `derived_from_artifact_id` — requirement ids → test-case artifacts → script artifacts. Then `TestExecutionResult` rows by `source_script_artifact_id`/`source_test_case_artifact_id`. Use set-based `IN` queries, not per-row loops.
  - [ ] Step 3 (AC6): collect generated artifacts that COULD belong to this source's family but have null lineage into `unmapped` (best-effort: Sarah sidecar + Mary name-match, flagged lower-confidence). Never mark them stale outright.
  - [ ] Return a Pydantic `StalenessImpact` (counts + lists of `{id, kind, name, title}` and exec-run summaries). Read-only; eager-load; `.unique()` on joined collections (AC7).

- [ ] **Task 4 — `StalenessImpact` payload model (AC: 5)**
  - [ ] Pydantic model in `src/ai_qa/models.py` (near the 18.2 `SourceChangeReport`) capturing the four asset tiers + `unmapped` + counts, serializable for the WS payload 18.4/18.5 will carry.

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Migration: column exists, self-FK, nullable, index; upgrade/downgrade clean; chains on 18.1's revision.
  - [ ] Save-path: Mary persists `derived_from_artifact_id` = requirement id when `source_requirement_id` set, null otherwise; Sarah persists = test-case id, and STILL writes the sidecar (regression — Jack reads it). Assert via the saved `Artifact` row.
  - [ ] Mapper: build a fixture chain (requirement R → test cases T1,T2 → scripts S1,S2 → exec results E1) all linked via `derived_from_artifact_id`/FKs; `map_impact(source of R)` returns exactly {R},{T1,T2},{S1,S2},{E1}. A test case with null lineage lands in `unmapped`, not in `test_cases`, and is NOT marked stale (AC6). A source with no requirement artifact returns empty tiers, no raise.
  - [ ] Read-only: assert the mapper issues no INSERT/UPDATE/DELETE (no DB mutation) — e.g. snapshot row counts unchanged after a call (AC7).
  - [ ] `uv run pytest` (full suite) + ruff + `mypy src`.

## Dev Notes

### The lineage gap is THE risk — read this first

Three independent forensic sweeps agree: today you CANNOT reliably answer "which test cases came from requirement R?" from the database. Mary's link (`source_requirement_id`) is computed ([test_case_extractor.py:292](src/ai_qa/pipelines/test_case_extractor.py:292)) and carried in memory but **dropped at save** ([mary.py:1306](src/ai_qa/agents/mary.py:1306) passes title/source_url/warnings but not the requirement id). The test-case markdown embeds the requirement NAME, not id, so reconstruction is name-matching — and 16.10 is about to flatten the folders that name-matching leans on. Sarah's link is in a sidecar JSON, queryable only by file read. Jack's link is the one real FK. Approach A fixes the two weak hops by persisting values that ALREADY EXIST in memory at save time — this is a small, low-risk change with a large payoff for the whole epic.

### Map by source provenance, not by markdown (AC4)

Requirement artifacts already carry first-class provenance: `kind="requirements"`, `name="{page_id}/requirement.md"` ([artifact_adapter.py:74](src/ai_qa/pipelines/artifact_adapter.py:74)), `parent_source_id`, `source_url`, `source_type` (set on approve, [artifact_adapter.py:84-97](src/ai_qa/pipelines/artifact_adapter.py:84)). The changed source's `source_id`/`source_url` (from 18.2) maps to requirement artifacts directly. Do NOT parse requirement markdown to find the source — the columns are authoritative.

### Current behavior to PRESERVE (regression guardrails)

- **Sarah's sidecar stays.** Jack reads `source_test_case_id` from the `.metadata.json` ([sarah.py:198](src/ai_qa/agents/sarah.py:198)); the new column is ADDITIVE, not a replacement. Removing the sidecar would break Jack ([db/models.py:380](src/ai_qa/db/models.py:380) population path).
- **Mapper mutates nothing (AC7).** It is a pure read. Persisting a stale flag or regenerating belongs to 18.4/18.5.
- **Async-DB rules.** Eager-load relationships, `.unique()` joined collections, never lazy-load in async ([[project-context]]). The artifact write path is sync `Session`; match the existing session style of whichever layer calls the mapper.
- **Legacy honesty (AC6).** Null-lineage assets are `unmapped`, never falsely "stale" — a false stale flag erodes trust in the whole feature.
- **16.10 interaction.** Story 16.10 (flat test-case/script storage, drop per-role subfolders) is `ready-for-dev` and changes artifact NAMES/paths. Approach A's `derived_from_artifact_id` is path-independent, so it is ROBUST to 16.10 — another reason to prefer A over name-matching.

### Source tree components to touch

- `src/ai_qa/db/models.py` — **UPDATE** (`Artifact.derived_from_artifact_id`).
- `alembic/versions/` — **ADD** (migration chaining on 18.1's revision).
- `src/ai_qa/artifacts/service.py` — **UPDATE** (`save_artifact` kwarg).
- `src/ai_qa/pipelines/artifact_adapter.py` — **UPDATE** (`save_test_case`, `save_script` kwargs).
- `src/ai_qa/agents/mary.py` — **UPDATE** (pass requirement id at [mary.py:1306](src/ai_qa/agents/mary.py:1306)).
- `src/ai_qa/agents/sarah.py` — **UPDATE** (pass test-case id at [sarah.py:1123](src/ai_qa/agents/sarah.py:1123)).
- `src/ai_qa/sources/staleness.py` — **ADD** (`StalenessMapper`).
- `src/ai_qa/models.py` — **ADD** (`StalenessImpact` payload).
- Tests — **ADD** for migration, save-paths, mapper.

### Decided scope (defaults — Thuong, correct if needed)

- **Approach A** (persist `derived_from_artifact_id`) — see the DECISION GATE above.
- **No persisted stale flag** in this story — the mapper returns the impact set on demand; persisting a stale marker is a deferred enhancement (18.4 can decide whether the cascade prompt needs it).
- **Best-effort legacy reconstruction**, clearly flagged as lower-confidence; never auto-promote a reconstructed link to "stale".

### Testing standards summary

- Backend pytest; build real `Artifact`/`TestExecutionResult` fixture chains in the test DB; assert exact set membership of each tier. Full-suite run for the coverage gate.
- No bare `pytest.raises(Exception)`; Pyrefly-clean (`session.get` returns `T | None` — filter; assert optionals).

### Project Structure Notes

- This story owns the SECOND Epic-18 migration (`derived_from_artifact_id`), chained onto 18.1's `source_snapshots`. If 18.1 is not yet merged, coordinate the `down_revision` so the chain is `273b69541e94` → 18.1 → 18.3.
- No FE in this story; the impact set is surfaced by 18.4/18.5.

### References

- Epic + story: [epics.md#Epic-18](_bmad-output/planning-artifacts/epics.md:2054), [Story 18.3](_bmad-output/planning-artifacts/epics.md:2074)
- Lineage facts: [test_case_extractor.py:292](src/ai_qa/pipelines/test_case_extractor.py:292) (Mary link computed), [mary.py:1306](src/ai_qa/agents/mary.py:1306) (dropped at save), [sarah.py:50](src/ai_qa/agents/sarah.py:50) + [sarah.py:198](src/ai_qa/agents/sarah.py:198) (Sarah sidecar), [db/models.py:377-382](src/ai_qa/db/models.py:377) (Jack FKs)
- Artifact + provenance: [db/models.py:227-266](src/ai_qa/db/models.py:227), [artifact_adapter.py:55-111](src/ai_qa/pipelines/artifact_adapter.py:55) (`save_requirement`), [artifact_adapter.py:142](src/ai_qa/pipelines/artifact_adapter.py:142) (`save_test_case`), [artifact_adapter.py:228](src/ai_qa/pipelines/artifact_adapter.py:228) (`save_script`)
- Save service: [service.py:79](src/ai_qa/artifacts/service.py:79)
- Migration chain: 18.1 `source_snapshots` → THIS; head was `273b69541e94`
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[mary-md-testcases-reports-cleanup]], [[artifact-ui-storage-overhaul]], [[verify-subagent-claims]], [[epic-14-jack-test-execution]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
