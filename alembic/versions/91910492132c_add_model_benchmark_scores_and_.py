"""add model benchmark scores and discovered models

Revision ID: 91910492132c
Revises: 7c2f9a3b1e84
Create Date: 2026-06-18 23:35:32.670490
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "91910492132c"
down_revision: str | Sequence[str] | None = "7c2f9a3b1e84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovered_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("supports_vision", sa.Boolean(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_discovered_models")),
        sa.UniqueConstraint("model_id", name="uq_discovered_models_model_id"),
    )
    op.create_table(
        "model_benchmark_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=255), nullable=False),
        sa.Column("capability", sa.String(length=50), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_model_benchmark_scores_updated_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_benchmark_scores")),
        sa.UniqueConstraint(
            "model_id", "capability", name="uq_model_benchmark_scores_model_capability"
        ),
    )
    op.create_index(
        "ix_model_benchmark_scores_model_id",
        "model_benchmark_scores",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_benchmark_scores_updated_by_user_id"),
        "model_benchmark_scores",
        ["updated_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_model_benchmark_scores_updated_by_user_id"),
        table_name="model_benchmark_scores",
    )
    op.drop_index("ix_model_benchmark_scores_model_id", table_name="model_benchmark_scores")
    op.drop_table("model_benchmark_scores")
    op.drop_table("discovered_models")
