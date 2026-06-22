"""add_provenance_columns_to_artifacts

Revision ID: c8e6ace95b08
Revises: 604f28c24393
Create Date: 2026-06-12 02:18:49.203871
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e6ace95b08"
down_revision: str | Sequence[str] | None = "604f28c24393"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("source_type", sa.String(length=50), nullable=True))
    op.add_column("artifacts", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("warnings", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("artifacts", "warnings")
    op.drop_column("artifacts", "source_url")
    op.drop_column("artifacts", "source_type")
