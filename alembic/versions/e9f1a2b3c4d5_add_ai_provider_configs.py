"""add ai_provider_configs table

Revision ID: e9f1a2b3c4d5
Revises: 7cef1ea1a837
Create Date: 2026-06-10 17:00:00.000000

Story 9.7 — Saved Provider Configuration and Rotation Behavior.

Creates ``ai_provider_configs`` table to store per-(user, project) non-secret
provider/model configuration as a default suggestion for future threads.
Secrets (API keys) remain exclusively in ``user_secrets`` — never here.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e9f1a2b3c4d5"
down_revision: str | Sequence[str] | None = "7cef1ea1a837"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("ai_provider_config", sa.JSON(), nullable=True),
        sa.Column("ai_agents_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "project_id", name="uq_ai_provider_configs_user_project"),
    )
    op.create_index("ix_ai_provider_configs_user_id", "ai_provider_configs", ["user_id"])
    op.create_index("ix_ai_provider_configs_project_id", "ai_provider_configs", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_ai_provider_configs_project_id", table_name="ai_provider_configs")
    op.drop_index("ix_ai_provider_configs_user_id", table_name="ai_provider_configs")
    op.drop_table("ai_provider_configs")
