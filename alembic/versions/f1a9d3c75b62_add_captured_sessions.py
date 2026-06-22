"""add captured_sessions (per-user encrypted browser sessions)

Revision ID: f1a9d3c75b62
Revises: e8c3b16a07d9
Create Date: 2026-06-20 00:00:02.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a9d3c75b62"
down_revision: str | Sequence[str] | None = "e8c3b16a07d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "captured_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("auth_method", sa.String(length=20), nullable=False),
        # Encrypted Playwright storageState JSON (app-level Fernet; DB column is plain TEXT).
        sa.Column("encrypted_storage_state", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_captured_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_captured_sessions_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_captured_sessions")),
        sa.UniqueConstraint(
            "user_id",
            "project_id",
            "environment",
            "role",
            name="uq_captured_sessions_user_project_env_role",
        ),
    )
    op.create_index(
        op.f("ix_captured_sessions_user_id"), "captured_sessions", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_captured_sessions_project_id"), "captured_sessions", ["project_id"], unique=False
    )
    op.create_index(
        "ix_captured_sessions_user_project",
        "captured_sessions",
        ["user_id", "project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_captured_sessions_user_project", table_name="captured_sessions")
    op.drop_index(op.f("ix_captured_sessions_project_id"), table_name="captured_sessions")
    op.drop_index(op.f("ix_captured_sessions_user_id"), table_name="captured_sessions")
    op.drop_table("captured_sessions")
