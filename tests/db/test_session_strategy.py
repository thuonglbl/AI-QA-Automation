"""Tests for DB session and migration strategy."""

from pathlib import Path
from unittest.mock import patch

from ai_qa.config import AppSettings
from ai_qa.db.health import check_database_health
from ai_qa.db.session import create_db_engine


def test_create_db_engine_is_lazy() -> None:
    settings = AppSettings(database_url="postgresql+psycopg://localhost:5432/app?user=test-user")

    engine = create_db_engine(settings)

    assert str(engine.url).startswith("postgresql+psycopg://localhost")


def test_database_health_not_configured_without_password_or_url() -> None:
    settings = AppSettings(database_url="", database_password="")

    health = check_database_health(settings)

    assert health.status == "not_configured"
    assert health.as_dict()["status"] == "not_configured"


def test_database_health_masks_connection_errors() -> None:
    settings = AppSettings(database_url="postgresql+psycopg://localhost:1/app?user=test-user")

    with patch("ai_qa.db.health.create_db_engine") as create_engine_mock:
        create_engine_mock.side_effect = RuntimeError("database connection failed for redacted URL")
        health = check_database_health(settings)

    assert health.status == "unhealthy"
    assert health.error == "database_unreachable"
    assert "<test-db-password>" not in str(health.as_dict())


def test_alembic_files_reference_core_schema() -> None:
    migration = Path("alembic/versions/20260504_1201_initial_core_schema.py").read_text()
    env = Path("alembic/env.py").read_text()

    assert "target_metadata = Base.metadata" in env
    for table_name in [
        "users",
        "projects",
        "project_memberships",
        "pipeline_runs",
        "artifacts",
        "artifact_versions",
        "audit_events",
    ]:
        assert f'"{table_name}"' in migration
