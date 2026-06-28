"""add users.avatar (Azure-synced profile photo, data URI)

Epic 23 (story 23.4): best-effort Azure-synced avatar, persisted on SSO login as a
``data:`` URI and served from our own backend. Nullable — air-gapped UAT (no Graph
egress) simply has no photo and the FE falls back to initials.

Revision ID: f2b3c4d5e6a7
Revises: e1a2c3d4f5b6
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2b3c4d5e6a7"
down_revision: str | Sequence[str] | None = "e1a2c3d4f5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar")
