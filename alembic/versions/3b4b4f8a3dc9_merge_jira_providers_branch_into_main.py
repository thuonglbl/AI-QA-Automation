"""Merge jira-providers branch into main

Revision ID: 3b4b4f8a3dc9
Revises: 60eb63abe6a6, a3f7d2e9b1c8
Create Date: 2026-06-09 00:07:04.326691
"""

from collections.abc import Sequence

revision: str = "3b4b4f8a3dc9"
down_revision: str | Sequence[str] | None = ("60eb63abe6a6", "a3f7d2e9b1c8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
