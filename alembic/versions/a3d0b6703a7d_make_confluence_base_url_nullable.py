"""make confluence_base_url nullable

Revision ID: a3d0b6703a7d
Revises: c5b1e9a4d762
Create Date: 2026-06-21 13:46:31.009063
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3d0b6703a7d"
down_revision: str | Sequence[str] | None = "c5b1e9a4d762"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "projects",
        "confluence_base_url",
        existing_type=sa.String(length=512),
        nullable=True,
    )


def downgrade() -> None:
    op.execute("UPDATE projects SET confluence_base_url = '' WHERE confluence_base_url IS NULL")
    op.alter_column(
        "projects",
        "confluence_base_url",
        existing_type=sa.String(length=512),
        nullable=False,
    )
