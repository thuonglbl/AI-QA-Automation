"""add_title_and_parent_source_id_to_artifacts

Revision ID: 7c2f9a3b1e84
Revises: c8e6ace95b08
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7c2f9a3b1e84"
down_revision: str | Sequence[str] | None = "c8e6ace95b08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("parent_source_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("artifacts", "parent_source_id")
    op.drop_column("artifacts", "title")
