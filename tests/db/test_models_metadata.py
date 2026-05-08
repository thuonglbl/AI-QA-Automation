"""Tests for SQLAlchemy ORM metadata."""

from sqlalchemy import UniqueConstraint

import ai_qa.db.models  # noqa: F401  # populate metadata
from ai_qa.db.base import Base


def test_core_tables_are_registered() -> None:
    expected_tables = {
        "users",
        "projects",
        "project_memberships",
        "pipeline_runs",
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
        "ix_pipeline_runs_project_status",
        "ix_artifacts_project_kind",
        "ix_audit_events_project_event_created",
    }
    actual_indexes = {
        index.name for table in Base.metadata.tables.values() for index in table.indexes
    }

    assert expected_indexes.issubset(actual_indexes)
