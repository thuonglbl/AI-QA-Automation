"""Tests for SQLAlchemy ORM metadata."""

from sqlalchemy import UniqueConstraint

import ai_qa.db.models  # noqa: F401  # populate metadata
import ai_qa.threads.models  # noqa: F401  # populate metadata
from ai_qa.db.base import Base


def test_core_tables_are_registered() -> None:
    expected_tables = {
        "users",
        "projects",
        "project_memberships",
        "threads",
        "agent_runs",
        "artifacts",
        "artifact_versions",
        "audit_events",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_required_unique_constraints_exist() -> None:
    memberships = Base.metadata.tables["project_memberships"]
    artifact_versions = Base.metadata.tables["artifact_versions"]

    membership_constraints = {
        constraint.name
        for constraint in memberships.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    version_constraints = {
        constraint.name
        for constraint in artifact_versions.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_project_memberships_project_user" in membership_constraints
    assert "uq_artifact_versions_artifact_version" in version_constraints


def test_lookup_indexes_exist() -> None:
    expected_indexes = {
        "ix_users_email",
        "ix_project_memberships_user_project",
        "ix_threads_project_user",
        "ix_agent_runs_thread_status",
        "ix_artifacts_project_kind",
        "ix_audit_events_project_event_created",
    }
    actual_indexes = {
        index.name for table in Base.metadata.tables.values() for index in table.indexes
    }

    assert expected_indexes.issubset(actual_indexes)


def test_pipeline_runs_are_retired_from_active_schema() -> None:
    assert "pipeline_runs" not in Base.metadata.tables

    artifacts = Base.metadata.tables["artifacts"]
    audit_events = Base.metadata.tables["audit_events"]

    assert "agent_run_id" in artifacts.columns
    assert "agent_run_id" in audit_events.columns
    assert "pipeline_run_id" not in artifacts.columns
    assert "pipeline_run_id" not in audit_events.columns


def test_agent_runs_are_artifact_and_audit_foreign_key_target() -> None:
    artifacts = Base.metadata.tables["artifacts"]
    audit_events = Base.metadata.tables["audit_events"]

    artifact_targets = {
        foreign_key.column.table.name
        for foreign_key in artifacts.columns["agent_run_id"].foreign_keys
    }
    audit_targets = {
        foreign_key.column.table.name
        for foreign_key in audit_events.columns["agent_run_id"].foreign_keys
    }

    assert artifact_targets == {"agent_runs"}
    assert audit_targets == {"agent_runs"}
