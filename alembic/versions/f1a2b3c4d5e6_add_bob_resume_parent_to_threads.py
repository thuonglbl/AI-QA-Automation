"""add bob_resume_parent to threads

Persists the confirmed Confluence parent of an in-flight Bob extraction so an
interrupted run (server restart / process death) can resume from the next
un-converted page without the user re-entering the URL/parent. Nullable; set
before extraction and cleared on successful completion. NULL means nothing to
resume, which is also what gates the "Continue" affordance.

Revision ID: f1a2b3c4d5e6
Revises: d9c4f1a6e2b8
Create Date: 2026-06-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "d9c4f1a6e2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "threads",
        sa.Column("bob_resume_parent", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("threads", "bob_resume_parent")
