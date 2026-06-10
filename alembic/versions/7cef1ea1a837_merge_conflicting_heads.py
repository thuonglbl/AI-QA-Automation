"""Merge conflicting heads

Revision ID: 7cef1ea1a837
Revises: 3b4b4f8a3dc9, 424bbf34f693
Create Date: 2026-06-09 00:34:06.957303
"""

from collections.abc import Sequence

revision: str = "7cef1ea1a837"
down_revision: str | Sequence[str] | None = ("3b4b4f8a3dc9", "424bbf34f693")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
