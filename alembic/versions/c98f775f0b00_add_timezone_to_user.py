"""add timezone to user

Revision ID: c98f775f0b00
Revises: 173fb95ecc4c
Create Date: 2026-06-20 07:38:28.220331
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c98f775f0b00"
down_revision: str | Sequence[str] | None = "173fb95ecc4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL on an existing table needs a server_default to backfill existing rows.
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
