"""add test_execution_results

Revision ID: a3f8d21c64b9
Revises: b2f5c9d81a34
Create Date: 2026-06-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3f8d21c64b9"
down_revision: str | Sequence[str] | None = "b2f5c9d81a34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_execution_results",
        sa.Column("agent_run_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("thread_id", sa.UUID(), nullable=True),
        sa.Column("source_script_artifact_id", sa.UUID(), nullable=True),
        sa.Column("source_test_case_artifact_id", sa.UUID(), nullable=True),
        sa.Column("test_name", sa.String(length=512), nullable=False),
        sa.Column("browser", sa.String(length=50), nullable=False, server_default="chromium"),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("failure_classification", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_test_execution_results_agent_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_test_execution_results_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["thread_id"],
            ["threads.id"],
            name=op.f("fk_test_execution_results_thread_id_threads"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_script_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_test_execution_results_source_script_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_test_case_artifact_id"],
            ["artifacts.id"],
            name=op.f("fk_test_execution_results_source_test_case_artifact_id_artifacts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_execution_results")),
    )
    op.create_index(
        op.f("ix_test_execution_results_agent_run_id"),
        "test_execution_results",
        ["agent_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_execution_results_project_id"),
        "test_execution_results",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_execution_results_thread_id"),
        "test_execution_results",
        ["thread_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_test_execution_results_source_script_artifact_id"),
        "test_execution_results",
        ["source_script_artifact_id"],
        unique=False,
    )
    op.create_index(
        "ix_test_execution_results_project_status",
        "test_execution_results",
        ["project_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_test_execution_results_project_status", table_name="test_execution_results")
    op.drop_index(
        op.f("ix_test_execution_results_source_script_artifact_id"),
        table_name="test_execution_results",
    )
    op.drop_index(op.f("ix_test_execution_results_thread_id"), table_name="test_execution_results")
    op.drop_index(op.f("ix_test_execution_results_project_id"), table_name="test_execution_results")
    op.drop_index(
        op.f("ix_test_execution_results_agent_run_id"), table_name="test_execution_results"
    )
    op.drop_table("test_execution_results")
