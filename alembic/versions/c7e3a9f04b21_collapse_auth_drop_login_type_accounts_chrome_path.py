"""collapse auth: drop login_type, project_accounts, users.chrome_path

Phase A of collapsing authentication to a single captured-session model. Removes the
PASSWORD/auto-login subsystem's persistence:

- ``projects.login_type`` (the SSO/PASSWORD switch)
- the ``project_accounts`` table (per-project test-login identities + encrypted password)
- ``users.chrome_path`` (per-user Chrome executable path)

Revision ID: c7e3a9f04b21
Revises: f1a2b3c4d5e6
Create Date: 2026-06-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7e3a9f04b21"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_project_accounts_project_id"), table_name="project_accounts")
    op.drop_table("project_accounts")
    op.drop_column("projects", "login_type")
    op.drop_column("users", "chrome_path")


def downgrade() -> None:
    op.add_column("users", sa.Column("chrome_path", sa.String(length=1024), nullable=True))
    op.add_column(
        "projects",
        sa.Column("login_type", sa.String(length=20), nullable=False, server_default="SSO"),
    )
    op.create_table(
        "project_accounts",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("login_identifier", sa.String(length=320), nullable=False),
        # Encrypted at the app layer (EncryptedText / db_encryption_key). TEXT-backed: the
        # Fernet ciphertext expands past the plaintext length and must not overflow a varchar.
        sa.Column("encrypted_password", sa.Text(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_accounts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_accounts")),
        sa.UniqueConstraint(
            "project_id", "environment", "role", name="uq_project_accounts_project_env_role"
        ),
    )
    op.create_index(
        op.f("ix_project_accounts_project_id"), "project_accounts", ["project_id"], unique=False
    )
