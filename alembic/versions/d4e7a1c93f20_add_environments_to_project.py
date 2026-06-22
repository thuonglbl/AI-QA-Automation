"""add environments to project

Revision ID: d4e7a1c93f20
Revises: c98f775f0b00
Create Date: 2026-06-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e7a1c93f20"
down_revision: str | Sequence[str] | None = "c98f775f0b00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Named target environments per project, e.g. [{"name": "...", "url": "..."}].
    # JSON array defaulting to empty list (no environments configured yet).
    op.add_column(
        "projects",
        sa.Column(
            "environments",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "environments")
