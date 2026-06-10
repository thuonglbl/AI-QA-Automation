"""Merge parallel branches

Revision ID: 424bbf34f693
Revises: 60eb63abe6a6, a3f7d2e9b1c8
Create Date: 2026-06-08 23:13:37.355336
"""

from collections.abc import Sequence

revision: str = "424bbf34f693"
down_revision: str | Sequence[str] | None = ("60eb63abe6a6", "a3f7d2e9b1c8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
