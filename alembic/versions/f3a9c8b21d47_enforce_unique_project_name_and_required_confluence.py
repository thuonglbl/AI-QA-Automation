"""enforce unique project name and required confluence_base_url

Revision ID: f3a9c8b21d47
Revises: a1b2c3d4e5f6
Create Date: 2026-06-06 17:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3a9c8b21d47"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add unique constraint on projects.name and make confluence_base_url NOT NULL."""
    bind = op.get_bind()

    # Story 8.3 AC2 / AC3: project names must be unique. Detect any existing
    # duplicates up-front so the migration aborts with a clear message instead
    # of failing mid-way on a UNIQUE violation.
    duplicates = bind.execute(
        sa.text("SELECT name, COUNT(*) AS c FROM projects GROUP BY name HAVING COUNT(*) > 1")
    ).fetchall()
    if duplicates:
        raise RuntimeError(
            "Cannot enforce unique project names: duplicate names exist: "
            f"{[(row[0], row[1]) for row in duplicates]}. "
            "Rename or remove duplicates before running this migration."
        )

    # Backfill any rows that predate the API-layer requirement so the
    # NOT NULL alter does not fail on legacy data.
    op.execute("UPDATE projects SET confluence_base_url = '' WHERE confluence_base_url IS NULL")

    op.alter_column(
        "projects",
        "confluence_base_url",
        existing_type=sa.String(length=512),
        nullable=False,
    )
    op.create_unique_constraint(op.f("uq_projects_name"), "projects", ["name"])


def downgrade() -> None:
    """Reverse the unique-name + required-confluence constraints."""
    op.drop_constraint(op.f("uq_projects_name"), "projects", type_="unique")
    op.alter_column(
        "projects",
        "confluence_base_url",
        existing_type=sa.String(length=512),
        nullable=True,
    )
