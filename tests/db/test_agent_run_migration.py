"""Regression tests for the pipeline_runs to agent_runs migration."""

from pathlib import Path

MIGRATION = Path("alembic/versions/0d5fd025248e_migrate_pipeline_runs_to_agent_runs.py").read_text()


def test_migration_preserves_pipeline_run_references_as_legacy_columns() -> None:
    assert "legacy_pipeline_run_id" in MIGRATION
    assert "drop_column('artifacts', 'pipeline_run_id')" not in MIGRATION
    assert "drop_column('audit_events', 'pipeline_run_id')" not in MIGRATION
    assert "drop_table('pipeline_runs')" not in MIGRATION


def test_migration_marks_pipeline_runs_legacy_instead_of_removing_table() -> None:
    assert "legacy_retired_at" in MIGRATION
    assert "legacy_retirement_note" in MIGRATION
    assert "Legacy table retained for historical references" in MIGRATION


def test_migration_adds_agent_run_foreign_keys_without_destroying_legacy_table() -> None:
    assert "fk_artifacts_agent_run_id_agent_runs" in MIGRATION
    assert "fk_audit_events_agent_run_id_agent_runs" in MIGRATION
    assert "agent_run_id" in MIGRATION
    assert "agent_runs" in MIGRATION
