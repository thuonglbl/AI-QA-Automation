"""add user_secrets, drop inline user keys

Revision ID: b7d2f1a9c4e5
Revises: f3a9c8b21d47
Create Date: 2026-06-07 01:00:00.000000

Story 9.1 — Encrypted Per-User Secret Storage Foundation.

Creates the ``user_secrets`` table (encrypted value separated from non-secret
metadata) and retires the legacy inline ``*_key`` columns on ``users``.

DEV-PHASE DATA NOTE: dropping the legacy columns discards any encrypted keys
currently stored on ``users``. This is acceptable in development — affected
users simply re-enter their provider/MCP keys through the Alice UI, which now
persists them into ``user_secrets``.
"""

from collections.abc import Sequence

import sqlalchemy as sa

import ai_qa.db.types
from alembic import op

revision: str = "b7d2f1a9c4e5"
down_revision: str | Sequence[str] | None = "f3a9c8b21d47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_secrets",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("secret_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("encrypted_value", sa.String(length=1024), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_secrets_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_secrets")),
        sa.UniqueConstraint("user_id", "secret_type", name="uq_user_secrets_user_secret_type"),
    )
    op.create_index(
        op.f("ix_user_secrets_user_id"),
        "user_secrets",
        ["user_id"],
        unique=False,
    )

    # Retire the legacy inline per-user key columns (migrated to user_secrets).
    op.drop_column("users", "browser_use_key")
    op.drop_column("users", "claude_key")
    op.drop_column("users", "gemini_key")
    op.drop_column("users", "openai_key")
    op.drop_column("users", "on_premises_key")
    op.drop_column("users", "mcp_key")


def downgrade() -> None:
    # Re-add the legacy columns mirroring migration e1287c77977a (EncryptedString(512)).
    op.add_column(
        "users",
        sa.Column("mcp_key", ai_qa.db.types.EncryptedString(length=512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("on_premises_key", ai_qa.db.types.EncryptedString(length=512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("openai_key", ai_qa.db.types.EncryptedString(length=512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("gemini_key", ai_qa.db.types.EncryptedString(length=512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("claude_key", ai_qa.db.types.EncryptedString(length=512), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("browser_use_key", ai_qa.db.types.EncryptedString(length=512), nullable=True),
    )

    op.drop_index(op.f("ix_user_secrets_user_id"), table_name="user_secrets")
    op.drop_table("user_secrets")
