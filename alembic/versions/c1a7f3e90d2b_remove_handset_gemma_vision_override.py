"""remove the hand-set gemma4-31b vision override (so benchmarks are pure llm-stats)

Operator decision (2026-06-25): ALL benchmark scores must come objectively from llm-stats,
with NO hand-set operator values. The only hand-set score left effective was
``inference-gemma4-31b`` / ``vision`` = 80.0 (seeded in 173fb95ecc4c, restored by
d9c4f1a6e2b8). This migration deletes that row.

On a re-synced local DB the row is already a fresh llm-stats value (~26.3); on a not-synced
target (e.g. UAT, where d9c4 left 80.0) this removes the stale hand-set value. Either way the
immediately-following transfer migration (d5e8c1b9f3a2) re-UPSERTs gemma's real llm-stats
scores, so the net result is the objective value, not 80.0.

NOTE: this migration was briefly removed and re-created — some local DBs were already stamped
at this revision, so the file must exist for alembic to locate it. ``DELETE`` is idempotent
(deleting a missing row is a no-op), so re-running order stays safe.

Revision ID: c1a7f3e90d2b
Revises: c7e3a9f04b21
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c1a7f3e90d2b"
down_revision: str | Sequence[str] | None = "c7e3a9f04b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM model_benchmark_scores "
            "WHERE model_id = 'inference-gemma4-31b' AND capability = 'vision'"
        )
    )


def downgrade() -> None:
    # Lossy: the prior value cannot be restored. No-op.
    pass
