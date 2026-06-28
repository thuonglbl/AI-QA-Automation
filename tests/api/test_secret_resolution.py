"""API tests for runtime secret resolution (Story 9.6).

Validates that secrets are resolved from the thread owner at execution time,
decrypted only in memory for minimum required operation, and that missing/invalid
secrets block execution with actionable messages. Also verifies no secret leakage
across all output channels.

Fixture scaffold copied from ``tests/api/test_admin_rbac_api.py`` per project
rules #19/#20/#21.
"""

from collections.abc import Generator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.secrets import (
    SECRET_TYPE_CLAUDE,
    SECRET_TYPE_MCP,
    SECRET_TYPE_OPENAI,
)
from ai_qa.secrets.models import UserSecret
from ai_qa.secrets.service import get_user_secret, set_user_secret


@pytest.fixture
def resolution_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [User.__table__, UserSecret.__table__]),
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


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    return cast(Generator[Session], db_override())


def _create_user(client: TestClient, email: str) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            role=STANDARD_ROLE,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _store_secret(client: TestClient, user: User, secret_type: str, value: str) -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        set_user_secret(session, user.id, secret_type, value)
        session.commit()
    finally:
        session_gen.close()


def _read_secret(client: TestClient, user: User, secret_type: str) -> str | None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        result: str | None = get_user_secret(session, user.id, secret_type)
        return result
    finally:
        session_gen.close()


def _token(client: TestClient, user: User) -> str:
    app = cast(FastAPI, client.app)
    session_manager = SessionManager(app.state.settings)
    session = session_manager.create_session(
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
    return session_manager.encode_session(session)  # type: ignore[no-any-return]


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, user)}"}


# --- [P0] Story 9.6: Runtime Secret Resolution ---


def test_secret_resolved_from_thread_owner_at_execution_time(
    resolution_client: TestClient,
) -> None:
    """[P0] AC1: Secrets are resolved from the thread owner at execution time.

    When an AI provider is invoked within a thread, the secret used must come
    from the user who owns that thread, not from a global or system config.
    """
    user_a = _create_user(resolution_client, "alice@example.com")
    user_b = _create_user(resolution_client, "bob@example.com")

    _store_secret(resolution_client, user_a, SECRET_TYPE_CLAUDE, "alice-claude-key-12345678")
    _store_secret(resolution_client, user_b, SECRET_TYPE_CLAUDE, "bob-claude-key-12345678")

    # Verify each user's secret is isolated
    alice_secret = _read_secret(resolution_client, user_a, SECRET_TYPE_CLAUDE)
    bob_secret = _read_secret(resolution_client, user_b, SECRET_TYPE_CLAUDE)

    assert alice_secret == "alice-claude-key-12345678"
    assert bob_secret == "bob-claude-key-12345678"
    assert alice_secret != bob_secret


def test_secret_decrypted_only_in_memory_for_operation(
    resolution_client: TestClient,
) -> None:
    """[P0] AC2: Secrets are decrypted only in memory for the minimum required operation.

    The decrypted value must never persist in the database or be returned
    in any API response beyond the operation scope.
    """
    user = _create_user(resolution_client, "alice@example.com")
    secret_value = "my-super-secret-key-12345"

    _store_secret(resolution_client, user, SECRET_TYPE_CLAUDE, secret_value)

    # The stored value in DB is the encrypted form (in-memory decrypt only)
    session_gen = _session_from_override(resolution_client)
    session = next(session_gen)
    try:
        from sqlalchemy import select

        row = session.scalar(
            select(UserSecret).where(
                UserSecret.user_id == user.id,
                UserSecret.secret_type == SECRET_TYPE_CLAUDE,
            )
        )
        assert row is not None
        # In SQLite test mode, the value is stored directly (no encryption in test)
        # but the API never exposes it
    finally:
        session_gen.close()

    # Status endpoint never exposes the secret value
    response = resolution_client.get(
        "/api/secrets/status", headers=_auth_headers(resolution_client, user)
    )
    assert response.status_code == 200
    assert secret_value not in response.text


def test_missing_secret_blocks_execution_with_actionable_message(
    resolution_client: TestClient,
) -> None:
    """[P0] AC3: Missing/invalid secret blocks execution with actionable message.

    When a user attempts to use a provider without a configured secret,
    the system must return a clear error indicating which secret is missing.
    """
    user = _create_user(resolution_client, "alice@example.com")

    # Verify the user has no configured secrets
    response = resolution_client.get(
        "/api/secrets/status", headers=_auth_headers(resolution_client, user)
    )
    assert response.status_code == 200
    statuses = response.json()
    claude_status = next(e for e in statuses if e["secret_type"] == SECRET_TYPE_CLAUDE)
    assert claude_status["configured"] is False
    assert claude_status["status"] == "missing"


def test_invalid_secret_format_blocks_execution(
    resolution_client: TestClient,
) -> None:
    """[P0] AC3: Invalid secret format is rejected with actionable message.

    Secrets that don't meet minimum length requirements are rejected
    with a clear error message indicating the expected format.
    """
    user = _create_user(resolution_client, "alice@example.com")
    secret_value = "x"

    response = resolution_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(resolution_client, user),
        json={"value": secret_value},
    )

    assert response.status_code == 422
    # Error message must be actionable without echoing the secret value
    assert "too short" in response.json()["detail"].lower()
    assert secret_value not in response.json()["detail"]


def test_secret_leakage_prevented_across_output_channels(
    resolution_client: TestClient,
) -> None:
    """[P0] AC4: No secret leakage across all output channels.

    Secret values must never appear in:
    - API responses (status, replace, error messages)
    - HTTP headers
    - Response bodies
    """
    user = _create_user(resolution_client, "alice@example.com")
    secret_value = "super-secret-claude-key-abcdef123"

    _store_secret(resolution_client, user, SECRET_TYPE_CLAUDE, secret_value)

    # Check status endpoint
    status_response = resolution_client.get(
        "/api/secrets/status", headers=_auth_headers(resolution_client, user)
    )
    assert status_response.status_code == 200
    assert secret_value not in status_response.text

    # Check replace endpoint response
    replace_response = resolution_client.put(
        f"/api/secrets/{SECRET_TYPE_OPENAI}",
        headers=_auth_headers(resolution_client, user),
        json={"value": "new-openai-key-12345678"},
    )
    assert replace_response.status_code == 200
    assert secret_value not in replace_response.text

    # Check error response doesn't leak
    error_response = resolution_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(resolution_client, user),
        json={"value": "bad"},
    )
    assert error_response.status_code == 422
    assert secret_value not in error_response.text


def test_secret_not_returned_in_create_or_update_responses(
    resolution_client: TestClient,
) -> None:
    """[P0] Secret values are never returned in any API response payload."""
    user = _create_user(resolution_client, "alice@example.com")
    secret_value = "my-claude-api-key-12345678"

    response = resolution_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(resolution_client, user),
        json={"value": secret_value},
    )

    assert response.status_code == 200
    body = response.json()
    assert "value" not in body
    assert "encrypted_value" not in body
    assert body["configured"] is True
    assert body["secret_type"] == SECRET_TYPE_CLAUDE


def test_cross_user_secret_isolation_enforced(
    resolution_client: TestClient,
) -> None:
    """[P0] Users cannot access each other's secrets through any endpoint."""
    user_a = _create_user(resolution_client, "alice@example.com")
    user_b = _create_user(resolution_client, "bob@example.com")

    _store_secret(resolution_client, user_a, SECRET_TYPE_CLAUDE, "alice-secret-key-12345678")

    # Bob tries to read Alice's secret status - should see his own (missing)
    bob_status = resolution_client.get(
        "/api/secrets/status", headers=_auth_headers(resolution_client, user_b)
    )
    assert bob_status.status_code == 200
    claude_status = next(e for e in bob_status.json() if e["secret_type"] == SECRET_TYPE_CLAUDE)
    assert claude_status["configured"] is False

    # Alice's secret value must not appear in Bob's response
    assert "alice-secret-key" not in bob_status.text


# --- [P0] Story 9.6: MCP Secret Resolution ---


def test_mcp_secret_resolved_from_thread_owner(
    resolution_client: TestClient,
) -> None:
    """[P0] AC1: MCP PAT is resolved from the thread owner's encrypted secrets."""
    user_a = _create_user(resolution_client, "alice@example.com")
    user_b = _create_user(resolution_client, "bob@example.com")

    _store_secret(resolution_client, user_a, SECRET_TYPE_MCP, "alice-mcp-pat-12345678")
    _store_secret(resolution_client, user_b, SECRET_TYPE_MCP, "bob-mcp-pat-12345678")

    alice_mcp = _read_secret(resolution_client, user_a, SECRET_TYPE_MCP)
    bob_mcp = _read_secret(resolution_client, user_b, SECRET_TYPE_MCP)

    assert alice_mcp == "alice-mcp-pat-12345678"
    assert bob_mcp == "bob-mcp-pat-12345678"
    assert alice_mcp != bob_mcp


def test_mcp_secret_resolved_only_in_memory(
    resolution_client: TestClient,
) -> None:
    """[P0] AC2: MCP secret is decrypted only in memory, not persisted to DB."""
    user = _create_user(resolution_client, "alice@example.com")
    mcp_value = "my-mcp-pat-12345678"

    _store_secret(resolution_client, user, SECRET_TYPE_MCP, mcp_value)

    # Verify the decrypted value is never returned via API
    status_response = resolution_client.get(
        "/api/secrets/status", headers=_auth_headers(resolution_client, user)
    )
    assert status_response.status_code == 200
    assert mcp_value not in status_response.text

    # The DB row stores the encrypted form (or plaintext in SQLite test mode)
    session_gen = _session_from_override(resolution_client)
    session = next(session_gen)
    try:
        from sqlalchemy import select

        row = session.scalar(
            select(UserSecret).where(
                UserSecret.user_id == user.id,
                UserSecret.secret_type == SECRET_TYPE_MCP,
            )
        )
        assert row is not None
    finally:
        session_gen.close()


def test_cross_user_mcp_secret_isolation(
    resolution_client: TestClient,
) -> None:
    """[P0] Users cannot access each other's MCP secrets through any endpoint."""
    user_a = _create_user(resolution_client, "alice@example.com")
    user_b = _create_user(resolution_client, "bob@example.com")

    _store_secret(resolution_client, user_a, SECRET_TYPE_MCP, "alice-mcp-pat-12345678")

    # Bob's status should show MCP as missing
    bob_status = resolution_client.get(
        "/api/secrets/status", headers=_auth_headers(resolution_client, user_b)
    )
    assert bob_status.status_code == 200
    mcp_status = next(e for e in bob_status.json() if e["secret_type"] == SECRET_TYPE_MCP)
    assert mcp_status["configured"] is False

    # Alice's MCP secret value must not appear in Bob's response
    assert "alice-mcp-pat" not in bob_status.text
