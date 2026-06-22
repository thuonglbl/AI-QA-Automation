"""add role to test_execution_results (Slice 6 role-grouped runs)

Revision ID: c5b1e9a4d762
Revises: a3f8d21c64b9
Create Date: 2026-06-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5b1e9a4d762"
down_revision: str | Sequence[str] | None = "a3f8d21c64b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Application role the test ran AS (the captured-session role its script belongs to).
    # Nullable — NULL for role-less / single-session runs and for rows written before Slice 6.
    op.add_column(
        "test_execution_results",
        sa.Column("role", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("test_execution_results", "role")
