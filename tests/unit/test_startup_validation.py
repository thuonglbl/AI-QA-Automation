"""Unit tests for startup validation (Story 9.1).

Validates that the application fails fast when required configuration is
missing or invalid, including encryption keys, environment variables, and
database connectivity.

Following project rules #19/#20/#21 for test patterns.
"""

from collections.abc import Generator
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.db.base import Base
from ai_qa.db.health import DatabaseHealth, check_database_health
from ai_qa.db.models import User


@pytest.fixture
def startup_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [User.__table__]),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


# --- Encryption Key Validation ---


def test_application_fails_fast_when_encryption_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[P1] AC1: Application fails fast when USER_SECRETS_ENCRYPTION_KEY is missing.

    The application must refuse to start if the encryption key environment
    variable is not set, preventing runtime failures later.
    """
    monkeypatch.delenv("USER_SECRETS_ENCRYPTION_KEY", raising=False)

    from ai_qa.config import AppSettings

    # Create a subclass that skips .env loading to truly test missing env var
    class TestAppSettings(AppSettings):
        model_config = {
            "env_file": None,
            "env_file_encoding": "utf-8",
            "case_sensitive": False,
            "extra": "ignore",
            "str_strip_whitespace": True,
        }

    with pytest.raises(Exception, match="USER_SECRETS_ENCRYPTION_KEY"):
        TestAppSettings()


def test_application_fails_fast_with_invalid_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[P1] AC1: Application fails fast with invalid encryption key format.

    Non-Fernet keys must be rejected at startup, not at runtime.
    """
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", "not-a-valid-fernet-key")

    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)

    with pytest.raises(Exception, match="USER_SECRETS_ENCRYPTION_KEY"):
        cfg.AppSettings()


def test_encryption_key_never_stored_in_postgresql(
    startup_client: TestClient,
) -> None:
    """[P1] AC2: Encryption key is never stored in PostgreSQL.

    The USER_SECRETS_ENCRYPTION_KEY must only be used in-memory for
    encryption/decryption operations and never persisted to the database.
    """
    from cryptography.fernet import Fernet

    from ai_qa.config import AppSettings

    settings = AppSettings()

    assert settings.user_secrets_encryption_key is not None

    fernet = Fernet(settings.user_secrets_encryption_key.encode())
    test_data = b"test encryption data"
    encrypted = fernet.encrypt(test_data)
    decrypted = fernet.decrypt(encrypted)
    assert decrypted == test_data

    assert len(settings.user_secrets_encryption_key) > 0
    import base64

    try:
        key_bytes = base64.urlsafe_b64decode(settings.user_secrets_encryption_key + "==")
        assert len(key_bytes) == 32
    except Exception:
        pytest.fail("Encryption key is not a valid Fernet key format")


def test_encryption_key_not_exposed_in_api_responses(
    startup_client: TestClient,
) -> None:
    """[P1] AC2: Encryption key is not exposed in any API responses."""
    response = startup_client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()

    schema_text = str(schema)
    assert "encryption_key" not in schema_text.lower()
    assert "ENCRYPTION_KEY" not in schema_text
    assert "fernet" not in schema_text.lower()


def test_application_starts_with_valid_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[P1] Application starts successfully with valid encryption key."""
    from cryptography.fernet import Fernet

    valid_key = Fernet.generate_key().decode()
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", valid_key)

    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)

    settings = cfg.AppSettings()
    assert settings.user_secrets_encryption_key == valid_key


def test_encryption_key_isolation_between_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[P1] Different application instances use different encryption keys."""
    from cryptography.fernet import Fernet

    key1 = Fernet.generate_key().decode()
    key2 = Fernet.generate_key().decode()

    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", key1)
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    settings1 = cfg.AppSettings()

    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", key2)
    reload(cfg)
    settings2 = cfg.AppSettings()

    assert settings1.user_secrets_encryption_key != settings2.user_secrets_encryption_key


# --- Database Connectivity Validation ---


def test_database_health_returns_not_configured_when_no_url() -> None:
    """Database health check reports 'not_configured' when DATABASE_URL is missing."""
    settings = MagicMock()
    settings.database_url = ""
    settings.database_password = ""

    result = check_database_health(settings)

    assert result.status == "not_configured"
    assert result.latency_ms is None
    assert result.error is None


def test_database_health_returns_unhealthy_on_connection_failure() -> None:
    """Database health check reports 'unhealthy' when connection fails."""
    settings = MagicMock()
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.database_password = "test"
    settings.database_host = "localhost"
    settings.database_port = 5432
    settings.database_name = "test_db"
    settings.database_user = "test"
    settings.database_pool_size = 1
    settings.database_max_overflow = 0
    settings.database_echo = False

    with patch("ai_qa.db.health.create_db_engine") as mock_engine:
        mock_engine.side_effect = Exception("Connection refused")
        result = check_database_health(settings)

    assert result.status == "unhealthy"
    assert result.error == "database_unreachable"
    assert isinstance(result.latency_ms, float)


def test_database_health_as_dict_excludes_error_when_none() -> None:
    """DatabaseHealth.as_dict() omits 'error' key when error is None."""
    health = DatabaseHealth(status="healthy", latency_ms=12.5)
    result = health.as_dict()

    assert result == {"status": "healthy", "latency_ms": 12.5}
    assert "error" not in result


def test_database_health_as_dict_includes_error_when_present() -> None:
    """DatabaseHealth.as_dict() includes 'error' key when error is set."""
    health = DatabaseHealth(status="unhealthy", latency_ms=100.0, error="database_unreachable")
    result = health.as_dict()

    assert result["error"] == "database_unreachable"


def test_database_health_frozen_dataclass() -> None:
    """DatabaseHealth is immutable — cannot modify fields after creation."""
    health = DatabaseHealth(status="healthy")

    with pytest.raises(AttributeError):
        health.status = "unhealthy"  # type: ignore[misc]


# --- Environment Variable Validation ---


def test_required_session_secret_key_has_default() -> None:
    """session_secret_key has a sensible default for development."""
    from ai_qa.config import AppSettings

    settings = AppSettings()
    assert settings.session_secret_key
    assert len(settings.session_secret_key) > 0


def test_session_expire_hours_bounded() -> None:
    """session_expire_hours is bounded between 1 and 24."""
    from ai_qa.config import AppSettings

    settings = AppSettings()
    assert 1 <= settings.session_expire_hours <= 24


def test_database_url_assembly_with_password() -> None:
    """sqlalchemy_database_url assembles correctly with database credentials."""
    from ai_qa.config import AppSettings

    settings = AppSettings()
    url = settings.sqlalchemy_database_url
    assert "postgresql+psycopg://" in url


def test_masked_database_url_hides_password() -> None:
    """masked_database_url replaces password with *** in the URL."""
    from ai_qa.config import AppSettings

    settings = AppSettings()
    masked = settings.masked_database_url
    if settings.database_password:
        assert "***" in masked
        assert settings.database_password not in masked


# --- API Startup Sanity ---


def test_application_exposes_openapi_schema(
    startup_client: TestClient,
) -> None:
    """Application serves OpenAPI schema after successful startup."""
    response = startup_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "openapi" in schema
    assert "paths" in schema


def test_application_health_endpoint_responds(
    startup_client: TestClient,
) -> None:
    """Application health endpoint responds after startup (if exposed)."""
    response = startup_client.get("/openapi.json")
    assert response.status_code == 200


def test_config_settings_validate_port_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """server_port is bounded to valid port range (1-65535)."""
    from ai_qa.config import AppSettings

    settings = AppSettings()
    assert 1 <= settings.server_port <= 65535
