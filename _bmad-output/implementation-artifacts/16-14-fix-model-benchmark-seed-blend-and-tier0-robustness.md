---
baseline_commit: 7641ef215742a18d6f5ca7951b6193abcf80164a
---
# Story 16.14: Fix model-benchmark seed blend & Alice Tier-0 robustness

Status: done

> **Priority: P0 (gating).** UAT finding #1 root cause. Until this ships + UAT is
> redeployed, Alice auto-selects the slow `qwen-vl-235b` family for every agent on UAT,
> which fails Confluence parsing and degrades the whole pipeline. Work right after 16-12.

## Story

As a QA user on a deployed (e.g. UAT) environment,
I want Alice to deterministically select the same sensible on-prem models it picks on local (glm-5.1 for reasoning/coding/instruction, a true vision model for Bob, a fast model for Jack),
so that extraction and generation work instead of routing a slow 235B vision model onto text roles.

### Observed bug

On UAT, Alice assigns `inference-qwen3-vl-235b` (`-GRC`) to **Alice, Bob, Mary and Sarah**; the model is slow and fails to parse most Confluence pages. Local picks glm-5.1 / gemma-31b / gpt-oss and runs fine. The two environments share code and `.env` structure (only `DATABASE_PASSWORD` differs) — the divergence is the data in `model_benchmark_scores`.

### Root cause (forensic, adversarially verified)

`_select_model_for` ([alice.py:557-560](src/ai_qa/agents/alice.py:557)) Tier-0 = admin scores from `model_benchmark_scores` win **outright**, with **no `-GRC` penalty** (the `non_grc` filter is Tier-1-only at [alice.py:500](src/ai_qa/agents/alice.py:500)). The two seed migrations blend destructively:

- Initial seed [`173fb95ecc4c`:218-223](alembic/versions/173fb95ecc4c_seed_discovered_models_and_benchmark_.py:218) gave `inference-qwen3-vl-235b-GRC` HIGH scores (reasoning 87 / vision 95 / instruction 86 / coding 78).
- Refresh [`273b69541e94`:611-618](alembic/versions/273b69541e94_seed_model_benchmarks_refresh.py:611) DELETE-then-INSERTs **only the model_ids it re-lists**, lowering the BASE `inference-qwen3-vl-235b` to ~14-24 and glm-51 to ~50, but **never lists `-GRC` in `_SCORES`** (only in `_DISCOVERED`).

So the stale `-GRC` high scores survive and become the top on-prem score for every capability → Tier-0 elects `inference-qwen3-vl-235b-GRC` for all four agents. A *clean* apply of head `273` alone would correctly elect glm-51 — the all-qwen symptom comes specifically from the **173→273 blend** leaving orphaned rows on a mismatched scale. The class is invisible to the SQLite test suite (both migrations `if dialect != 'postgresql': return`).

## Acceptance Criteria

1. **Consistent on-prem score scale.** Given a database migrated to head, when the on-prem benchmark scores are read, then the stale orphaned rows the `273` refresh failed to overwrite (the `-GRC` duplicates + the initial-seed-only ids) are gone, leaving a single consistent score scale.
2. **Correct deterministic mapping.** Given the cleaned scores, when Alice assigns models on the on-prem pool, then Alice/Mary/Sarah resolve to `inference-glm-51-754b` (reasoning/instruction/coding) and Bob resolves to a true vision model (`inference-gemma4-31b`), matching the known-good local mapping.
3. **Tier-0 ignores zero/negative scores.** Given a `model_benchmark_scores` row with score `<= 0`, when selection runs, then that row does NOT make the model a Tier-0 winner; selection falls through to the curated tier.
4. **Tier-0 de-prioritizes `-GRC` duplicates.** Given a stale `-GRC` row outscores its non-GRC sibling, when selection runs, then the non-GRC model is preferred (the `-GRC` variant only wins when it is the sole scored eligible model).
5. **No regression to existing selection behavior.** Given the existing golden-table / curated / parsed / promote tests, when the suite runs, then all still pass; a legitimate positive non-GRC admin score still overrides curated.

## Tasks / Subtasks

- [x] **Task 1 — Migration to complete the refresh's replace-snapshot (AC1, AC2)**
  - [x] New migration `d9c4f1a6e2b8` (`down_revision = 273b69541e94`, the prior head) deleting `model_benchmark_scores` rows for the **16** orphaned ids the `273` refresh did not re-score — exactly `set(173._SCORES) - set(273._SCORES)` (`-GRC` variants + `inference-apertus-70b`/`inference-gemma-12b-it`/`inference-granite-vision-2b`/`inference-qwen3-8b`/`inference-mistral-v03-7b`/`on-premises-corp-gpt-osslatest`/`claude-g5`/`claude-oss`/`ask-*`/`chat-*`/`Anthropic/Claude-GPT-OSS-120B`/`inference-bl`). **(Adversarial review caught a missing `inference-granite-vision-2b` — its stale vision 45.0 would have made Bob pick the weak 2B model; now included + locked by a completeness test.)**
  - [x] Restore the on-prem vision workhorse: upsert `inference-gemma4-31b` vision = 80.0 (the `173` operator value the refresh dropped) so Bob **deterministically** selects gemma4-31b over the slow qwen-vl-235b, independent of whatever `supports_vision` flag the live gateway reports for text models.
  - [x] Postgres-only guard (`if bind.dialect.name != "postgresql": return`); `discovered_models` rows left intact; downgrade is a documented lossy no-op.
- [x] **Task 2 — Tier-0 robustness in `_select_model_for` (AC3, AC4)**
  - [x] Drop non-positive scores when building the Tier-0 `scored` list.
  - [x] Restrict to non-GRC scored candidates when any exist (mirror Tier-1 `non_grc` at [alice.py:500](src/ai_qa/agents/alice.py:500)); `-GRC` still selectable when it is the only scored eligible model.
- [x] **Task 3 — Tests (all ACs)**
  - [x] `tests/test_agents/test_alice_tier0_robustness.py`: `-GRC` does not beat non-GRC sibling; only-GRC still selectable; 0.0 treated as unscored; positive non-GRC still overrides curated.
  - [x] `tests/db/test_orphaned_benchmark_migration.py`: asserts `_ORPHANED_SCORE_MODEL_IDS == set(173._SCORES) - set(273._SCORES)` (drift guard; catches the granite miss) and that both the culprit `-GRC` id and `granite-vision-2b` are covered.
  - [x] Full backend suite stays green (1811 passed; existing alice golden-table tests unchanged).
  - Post-migration Tier-0 mapping (verified by review recomputation): alice/mary/sarah → `inference-glm-51-754b`, **bob → `inference-gemma4-31b`** (vision 80), jack → `inference-gpt-oss-120b`.
- [ ] **Task 4 — Verification gates**
  - [ ] `uv run ruff check --fix src/ tests/` + `uv run ruff format` + `uv run mypy src`.
  - [ ] `uv run pytest` green.
  - [ ] **Deploy step (Thuong):** `uv run alembic upgrade head` on UAT + rebuild/redeploy backend image. Confirm on UAT: `SELECT model_id,capability,score FROM model_benchmark_scores WHERE model_id LIKE 'inference-qwen3-vl-235b%';` shows no `-GRC` rows, and a fresh Alice run assigns glm-51 / gemma.

## Files changed

- `alembic/versions/d9c4f1a6e2b8_fix_orphaned_onprem_benchmark_scores.py` (new — orphan delete + gemma vision restore)
- `src/ai_qa/agents/alice.py` (`_select_model_for` Tier-0 guard)
- `tests/test_agents/test_alice_tier0_robustness.py` (new)
- `tests/db/test_orphaned_benchmark_migration.py` (new — delete-list completeness drift guard)

## Notes / deferred

- The `fast` scores in `273` (`inference-gpt-oss-120b` = 500.0, etc.) are an llm-stats throughput value loaded as a quality score; they happen to keep Jack on gpt-oss (the desired local behavior), so they are intentionally left unchanged here and noted for a future scale-normalization pass.
- The durable provisioning of correct offline scores for the air-gapped UAT host is [16-18](16-18-restore-model-transfer-and-offline-benchmark-provisioning.md).
