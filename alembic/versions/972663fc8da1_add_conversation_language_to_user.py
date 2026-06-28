"""add_conversation_language_to_user

Revision ID: 972663fc8da1
Revises: 2c89cf36f942
Create Date: 2026-06-26 10:19:26.076242
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "972663fc8da1"
down_revision: str | Sequence[str] | None = "2c89cf36f942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL on an existing table needs a server_default to backfill existing rows.
    op.add_column(
        "users",
        sa.Column(
            "conversation_language", sa.String(length=10), nullable=False, server_default="en"
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "conversation_language")
