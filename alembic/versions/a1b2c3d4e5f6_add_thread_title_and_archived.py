"""Add title and is_archived to threads

Revision ID: a1b2c3d4e5f6
Revises: 8f604df875ba
Create Date: 2026-06-06 00:56:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "8f604df875ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("threads", sa.Column("title", sa.String(length=255), nullable=True))
    op.add_column(
        "threads",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Drop the server_default now that existing rows are backfilled with false.
    op.alter_column("threads", "is_archived", server_default=None)


def downgrade() -> None:
    op.drop_column("threads", "is_archived")
    op.drop_column("threads", "title")
