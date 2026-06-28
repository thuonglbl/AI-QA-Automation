"""fix orphaned on-prem benchmark scores left by the 273 refresh

The refresh seed (273b69541e94) was meant to replace the whole on-prem benchmark
snapshot, but its score overwrite only DELETEs the model_ids it itself re-lists. So the
on-prem ids that the INITIAL seed (173fb95ecc4c) scored but the refresh omitted kept
their stale initial-seed rows — on a different (higher) score scale, and including the
"-GRC" duplicate variants. The worst offender, ``inference-qwen3-vl-235b-GRC``
(reasoning 87 / vision 95 / instruction 86 / coding 78), then won Alice's Tier-0
selection for EVERY agent on a freshly-migrated database (e.g. UAT), routing the slow
235B vision model onto the text roles and breaking extraction.

This migration completes the refresh's intended replace-snapshot by deleting those
orphaned score rows, leaving a single consistent score scale (the 273 refresh values),
so Alice once again selects glm-51 for the reasoning/coding/instruction roles. It also
restores the on-prem vision score for ``inference-gemma4-31b`` (dropped by the 273
refresh) so Bob deterministically selects that fast vision model rather than the slow
``qwen-vl-235b`` or a text model the gateway happens to flag vision-capable. Idempotent
(plain DELETE + an upsert) and Postgres-only (tests build the schema via create_all, not
migrations).

Revision ID: d9c4f1a6e2b8
Revises: 273b69541e94
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9c4f1a6e2b8"
down_revision: str | Sequence[str] | None = "273b69541e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Model ids seeded by 173fb95ecc4c whose benchmark scores the 273 refresh did NOT
# re-write (so they kept stale initial-seed values on a mismatched scale, including the
# "-GRC" duplicates). Deleting their model_benchmark_scores rows leaves only the
# refreshed, consistent scores. discovered_models rows are left intact (the models still
# exist in the pool); only the stale benchmark SCORES are removed.
_ORPHANED_SCORE_MODEL_IDS: list[str] = [
    "Anthropic/Claude-GPT-OSS-120B",
    "ask-your-corp-confluence",
    "ask-your-corp-jira",
    "chat-with-corp-mcp",
    "claude-g5",
    "claude-oss",
    "inference-apertus-70b",
    "inference-apertus-70b-GRC",
    "inference-bl",
    "inference-gemma-12b-it",
    "inference-gemma4-31b-GRC",
    "inference-granite-vision-2b",
    "inference-mistral-v03-7b",
    "inference-qwen3-8b",
    "inference-qwen3-vl-235b-GRC",
    "on-premises-corp-gpt-osslatest",
]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    # 1. Delete the orphaned rows the 273 refresh failed to overwrite, leaving a single
    #    consistent (273) score scale for the on-prem pool.
    op.execute(
        sa.text("DELETE FROM model_benchmark_scores WHERE model_id IN :ids").bindparams(
            sa.bindparam("ids", value=_ORPHANED_SCORE_MODEL_IDS, expanding=True)
        )
    )

    # 2. Restore the on-prem vision workhorse. The 273 refresh dropped
    #    inference-gemma4-31b's vision score (llm-stats has no vision benchmark for it),
    #    which removed the team's designated FAST on-prem vision model from contention.
    #    Bob's selection is vision-gated but Tier-0 still picks the highest-scored
    #    vision-eligible model by capability score, and without a real vision row gemma's
    #    vision score falls back to its (low) global score — so Bob's pick would depend on
    #    whatever text model the live gateway happens to flag vision-capable. Restoring the
    #    operator vision score (the 173fb95ecc4c value, 80.0) makes Bob deterministically
    #    select gemma4-31b over the slow qwen-vl-235b, matching the known-good local mapping.
    scores = sa.table(
        "model_benchmark_scores",
        sa.column("id", sa.Uuid),
        sa.column("model_id", sa.String),
        sa.column("capability", sa.String),
        sa.column("score", sa.Float),
        sa.column("note", sa.Text),
        sa.column("updated_by_user_id", sa.Uuid),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        pg_insert(scores)
        .values(
            id=sa.func.gen_random_uuid(),
            model_id="inference-gemma4-31b",
            capability="vision",
            score=80.0,
            note=None,
            updated_by_user_id=None,
            created_at=sa.func.now(),
            updated_at=sa.func.now(),
        )
        .on_conflict_do_update(
            index_elements=["model_id", "capability"],
            set_={"score": 80.0, "updated_at": sa.func.now()},
        )
    )


def downgrade() -> None:
    # Lossy: the deleted rows were stale duplicates from an earlier seed (173fb95ecc4c)
    # already superseded by the 273 refresh; they are not restored on downgrade. The
    # restored gemma4-31b vision row is left in place (harmless and intended).
    pass
