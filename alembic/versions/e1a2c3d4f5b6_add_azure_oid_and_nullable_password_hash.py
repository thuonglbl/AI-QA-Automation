"""add azure_oid and make users.password_hash nullable

Epic 23 (story 23.3): SSO-first auth.

- ``users.azure_oid`` (nullable, unique) — the stable Entra object id used as the
  cross-login join key (email/UPN can change). Populated on first SSO provision.
- ``users.password_hash`` becomes NULLABLE — SSO-provisioned users have no local
  password. (The column is dropped entirely in story 23.6.)

Revision ID: e1a2c3d4f5b6
Revises: d5e8c1b9f3a2
Create Date: 2026-06-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1a2c3d4f5b6"
down_revision: str | Sequence[str] | None = "d5e8c1b9f3a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Single batch block keeps it correct on Postgres (direct ALTERs) and SQLite
    # (table recreate retains the new column + index + relaxed nullability together).
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("azure_oid", sa.String(length=64), nullable=True))
        batch_op.alter_column("password_hash", existing_type=sa.String(length=255), nullable=True)
        batch_op.create_index(op.f("ix_users_azure_oid"), ["azure_oid"], unique=True)


def downgrade() -> None:
    # NOTE: downgrade restores the column SHAPE (NOT NULL). Any password-less SSO
    # users would violate the constraint — backfill before downgrading.
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index(op.f("ix_users_azure_oid"))
        batch_op.alter_column("password_hash", existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column("azure_oid")
