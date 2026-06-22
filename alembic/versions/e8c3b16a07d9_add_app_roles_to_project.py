"""add app_roles to project

Revision ID: e8c3b16a07d9
Revises: d4e7a1c93f20
Create Date: 2026-06-20 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8c3b16a07d9"
down_revision: str | Sequence[str] | None = "d4e7a1c93f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # App-under-test role names (e.g. ["Admin", "User"]); JSON array defaulting to [].
    op.add_column(
        "projects",
        sa.Column(
            "app_roles",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "app_roles")
