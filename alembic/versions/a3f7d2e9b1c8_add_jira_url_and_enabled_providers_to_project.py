"""add jira_base_url and enabled_providers to project

Revision ID: a3f7d2e9b1c8
Revises: 02eee99fe6ae
Create Date: 2026-06-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f7d2e9b1c8"
down_revision: str | Sequence[str] | None = "02eee99fe6ae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Make confluence_base_url nullable (was NOT NULL default "")
    op.alter_column("projects", "confluence_base_url", nullable=True)

    # Add optional Jira base URL
    op.add_column(
        "projects",
        sa.Column("jira_base_url", sa.String(length=512), nullable=True),
    )

    # Add enabled_providers as a JSON array, defaulting to empty list
    op.add_column(
        "projects",
        sa.Column(
            "enabled_providers",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "enabled_providers")
    op.drop_column("projects", "jira_base_url")
    # Restore confluence_base_url to NOT NULL with empty string default
    op.alter_column("projects", "confluence_base_url", nullable=False, server_default="")
