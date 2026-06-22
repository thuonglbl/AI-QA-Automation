"""model benchmark score int to float

Revision ID: 8b1189329f95
Revises: 91910492132c
Create Date: 2026-06-19 11:53:24.532657
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8b1189329f95"
down_revision: str | Sequence[str] | None = "91910492132c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "model_benchmark_scores",
        "score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using="score::double precision",
    )


def downgrade() -> None:
    op.alter_column(
        "model_benchmark_scores",
        "score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="score::integer",
    )
