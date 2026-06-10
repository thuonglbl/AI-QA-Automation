"""migrate_pipeline_runs_to_agent_runs

Revision ID: 0d5fd025248e
Revises: 545019f951da
Create Date: 2026-06-04 21:40:05.119674
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0d5fd025248e"
down_revision: str | Sequence[str] | None = "545019f951da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Move active run references to agent_runs while preserving legacy linkage."""
    op.add_column("artifacts", sa.Column("agent_run_id", sa.UUID(), nullable=True))
    op.drop_index(op.f("ix_artifacts_pipeline_run_id"), table_name="artifacts")
    op.drop_constraint(
        op.f("fk_artifacts_pipeline_run_id_pipeline_runs"), "artifacts", type_="foreignkey"
    )
    op.alter_column("artifacts", "pipeline_run_id", new_column_name="legacy_pipeline_run_id")
    op.create_index(
        op.f("ix_artifacts_legacy_pipeline_run_id"),
        "artifacts",
        ["legacy_pipeline_run_id"],
        unique=False,
    )
    op.create_index(op.f("ix_artifacts_agent_run_id"), "artifacts", ["agent_run_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_artifacts_agent_run_id_agent_runs"),
        "artifacts",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("audit_events", sa.Column("agent_run_id", sa.UUID(), nullable=True))
    op.drop_index(op.f("ix_audit_events_pipeline_run_id"), table_name="audit_events")
    op.drop_constraint(
        op.f("fk_audit_events_pipeline_run_id_pipeline_runs"),
        "audit_events",
        type_="foreignkey",
    )
    op.alter_column("audit_events", "pipeline_run_id", new_column_name="legacy_pipeline_run_id")
    op.create_index(
        op.f("ix_audit_events_legacy_pipeline_run_id"),
        "audit_events",
        ["legacy_pipeline_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_audit_events_agent_run_id"), "audit_events", ["agent_run_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_audit_events_agent_run_id_agent_runs"),
        "audit_events",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column(
        "pipeline_runs",
        sa.Column(
            "legacy_retired_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Legacy marker retained for historical pipeline run references.",
        ),
    )
    op.add_column(
        "pipeline_runs",
        sa.Column(
            "legacy_retirement_note",
            sa.Text(),
            nullable=True,
            comment="Explains that new run relationships use agent_runs.",
        ),
    )
    op.execute(
        "UPDATE pipeline_runs "
        "SET legacy_retirement_note = "
        "'Legacy table retained for historical references; new artifacts and audit events use agent_runs.'"
    )


def downgrade() -> None:
    """Restore active pipeline_run_id references for downgrade compatibility."""
    op.drop_column("pipeline_runs", "legacy_retirement_note")
    op.drop_column("pipeline_runs", "legacy_retired_at")

    op.drop_constraint(
        op.f("fk_audit_events_agent_run_id_agent_runs"), "audit_events", type_="foreignkey"
    )
    op.drop_index(op.f("ix_audit_events_agent_run_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_legacy_pipeline_run_id"), table_name="audit_events")
    op.alter_column("audit_events", "legacy_pipeline_run_id", new_column_name="pipeline_run_id")
    op.create_foreign_key(
        op.f("fk_audit_events_pipeline_run_id_pipeline_runs"),
        "audit_events",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_audit_events_pipeline_run_id"), "audit_events", ["pipeline_run_id"], unique=False
    )
    op.drop_column("audit_events", "agent_run_id")

    op.drop_constraint(
        op.f("fk_artifacts_agent_run_id_agent_runs"), "artifacts", type_="foreignkey"
    )
    op.drop_index(op.f("ix_artifacts_agent_run_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_legacy_pipeline_run_id"), table_name="artifacts")
    op.alter_column("artifacts", "legacy_pipeline_run_id", new_column_name="pipeline_run_id")
    op.create_foreign_key(
        op.f("fk_artifacts_pipeline_run_id_pipeline_runs"),
        "artifacts",
        "pipeline_runs",
        ["pipeline_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_artifacts_pipeline_run_id"), "artifacts", ["pipeline_run_id"], unique=False
    )
    op.drop_column("artifacts", "agent_run_id")
