"""API tests for the per-user secret status and replacement routes (Story 9.2).

Fixture scaffold copied from ``tests/api/test_admin_rbac_api.py`` per project
rules #19/#20/#21 (in-memory SQLite ``StaticPool``, ``cast(list[Table], ...)``
in ``create_all``, ``cast(FastAPI, client.app)`` for app access,
``dependency_overrides`` wiring, and ``engine.dispose()`` teardown).
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
from ai_qa.api.secrets import PROVIDER_DISPLAY_NAMES
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.secrets import (
    CANONICAL_SECRET_TYPES,
    SECRET_TYPE_CLAUDE,
    SECRET_TYPE_GEMINI,
    SECRET_TYPE_OPENAI,
)
from ai_qa.secrets.models import UserSecret
from ai_qa.secrets.service import MIN_SECRET_LENGTH, get_user_secret, set_user_secret


@pytest.fixture
def secrets_client() -> Generator[TestClient]:
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
        return get_user_secret(session, user.id, secret_type)
    finally:
        session_gen.close()


def _count_rows(client: TestClient, user: User, secret_type: str) -> int:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        return (
            session.query(UserSecret)
            .filter(UserSecret.user_id == user.id, UserSecret.secret_type == secret_type)
            .count()
        )
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


# --- AC1: status returns non-secret fields only ---


def test_status_lists_all_canonical_types_with_metadata_only(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")
    _store_secret(secrets_client, user, SECRET_TYPE_CLAUDE, "claude-secret-value")

    response = secrets_client.get(
        "/api/secrets/status", headers=_auth_headers(secrets_client, user)
    )

    assert response.status_code == 200
    statuses = response.json()
    assert {entry["secret_type"] for entry in statuses} == set(CANONICAL_SECRET_TYPES)
    for entry in statuses:
        assert set(entry.keys()) == {
            "secret_type",
            "provider_name",
            "configured",
            "status",
            "validation_state",
            "last_updated",
        }
        # No secret-bearing fields anywhere in the payload.
        assert "value" not in entry
        assert "encrypted_value" not in entry

    claude = next(e for e in statuses if e["secret_type"] == SECRET_TYPE_CLAUDE)
    openai = next(e for e in statuses if e["secret_type"] == SECRET_TYPE_OPENAI)
    assert claude["configured"] is True
    assert claude["provider_name"] == "Claude"
    assert claude["last_updated"] is not None
    assert openai["configured"] is False
    assert openai["status"] == "missing"


def test_status_never_leaks_stored_plaintext(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")
    secret_value = "super-secret-claude-key-abc123"
    _store_secret(secrets_client, user, SECRET_TYPE_CLAUDE, secret_value)

    response = secrets_client.get(
        "/api/secrets/status", headers=_auth_headers(secrets_client, user)
    )

    assert response.status_code == 200
    assert secret_value not in response.text


# --- AC2: replacement stores and supersedes the previous value ---


def test_replace_stores_new_value_for_future_runs(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "fresh-claude-key-001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["secret_type"] == SECRET_TYPE_CLAUDE
    assert body["configured"] is True
    assert "value" not in body and "encrypted_value" not in body
    # Future runs use the new (stripped) value.
    assert _read_secret(secrets_client, user, SECRET_TYPE_CLAUDE) == "fresh-claude-key-001"


def test_replace_strips_value_before_storing(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "   padded-claude-key   "},
    )

    assert response.status_code == 200
    assert _read_secret(secrets_client, user, SECRET_TYPE_CLAUDE) == "padded-claude-key"


def test_replace_supersedes_previous_value_without_duplicate_row(
    secrets_client: TestClient,
) -> None:
    user = _create_user(secrets_client, "user@example.com")
    _store_secret(secrets_client, user, SECRET_TYPE_CLAUDE, "original-key-value")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "rotated-key-value"},
    )

    assert response.status_code == 200
    assert _count_rows(secrets_client, user, SECRET_TYPE_CLAUDE) == 1
    assert _read_secret(secrets_client, user, SECRET_TYPE_CLAUDE) == "rotated-key-value"


def test_replace_accepts_matching_secret_type_in_body(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_OPENAI}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "openai-key-12345", "secret_type": SECRET_TYPE_OPENAI},
    )

    assert response.status_code == 200


def test_replace_rejects_mismatched_secret_type_in_body(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_OPENAI}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "openai-key-12345", "secret_type": SECRET_TYPE_CLAUDE},
    )

    assert response.status_code == 400


# --- AC2 validation: empty / whitespace / short / unknown type ---


@pytest.mark.parametrize("bad_value", ["", "       "])
def test_replace_rejects_empty_or_whitespace_values(
    secrets_client: TestClient, bad_value: str
) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": bad_value},
    )

    assert response.status_code == 422


def test_replace_rejects_invalid_value_without_echoing_it(
    secrets_client: TestClient,
) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "ab12"},
    )

    assert response.status_code == 422
    # The submitted value must not be reflected back in the error body.
    assert "ab12" not in response.text


def test_replace_rejects_unknown_secret_type(secrets_client: TestClient) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        "/api/secrets/not-a-real-provider",
        headers=_auth_headers(secrets_client, user),
        json={"value": "some-valid-key-123"},
    )

    assert response.status_code == 422


# --- AC3 / ownership: auth required; users only see/replace their own secrets ---


def test_status_requires_authentication(secrets_client: TestClient) -> None:
    response = secrets_client.get("/api/secrets/status")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_replace_requires_authentication(secrets_client: TestClient) -> None:
    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        json={"value": "fresh-claude-key-001"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_user_only_sees_own_secret_status(secrets_client: TestClient) -> None:
    alice = _create_user(secrets_client, "alice@example.com")
    bob = _create_user(secrets_client, "bob@example.com")
    _store_secret(secrets_client, alice, SECRET_TYPE_CLAUDE, "alice-only-secret-value")

    response = secrets_client.get("/api/secrets/status", headers=_auth_headers(secrets_client, bob))

    assert response.status_code == 200
    bob_claude = next(e for e in response.json() if e["secret_type"] == SECRET_TYPE_CLAUDE)
    assert bob_claude["configured"] is False
    # Bob's response never contains Alice's stored value.
    assert "alice-only-secret-value" not in response.text


def test_replace_only_affects_own_secret(secrets_client: TestClient) -> None:
    alice = _create_user(secrets_client, "alice@example.com")
    bob = _create_user(secrets_client, "bob@example.com")
    _store_secret(secrets_client, alice, SECRET_TYPE_CLAUDE, "alice-original-value")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, bob),
        json={"value": "bob-new-claude-value"},
    )

    assert response.status_code == 200
    # Alice's secret is untouched by Bob's replacement.
    assert _read_secret(secrets_client, alice, SECRET_TYPE_CLAUDE) == "alice-original-value"
    assert _read_secret(secrets_client, bob, SECRET_TYPE_CLAUDE) == "bob-new-claude-value"


# --- AC1: provider display-name mapping + zero-secret baseline ---


def test_status_for_new_user_reports_every_type_missing(secrets_client: TestClient) -> None:
    """A user who has never stored a secret sees every canonical type as missing."""
    user = _create_user(secrets_client, "fresh@example.com")

    response = secrets_client.get(
        "/api/secrets/status", headers=_auth_headers(secrets_client, user)
    )

    assert response.status_code == 200
    statuses = response.json()
    assert {entry["secret_type"] for entry in statuses} == set(CANONICAL_SECRET_TYPES)
    assert all(entry["configured"] is False for entry in statuses)
    assert all(entry["status"] == "missing" for entry in statuses)
    assert all(entry["validation_state"] == "missing" for entry in statuses)
    assert all(entry["last_updated"] is None for entry in statuses)


def test_status_maps_human_readable_provider_names_for_all_types(
    secrets_client: TestClient,
) -> None:
    """Every canonical type carries its UX-sourced human-readable label."""
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.get(
        "/api/secrets/status", headers=_auth_headers(secrets_client, user)
    )

    assert response.status_code == 200
    names_by_type = {entry["secret_type"]: entry["provider_name"] for entry in response.json()}
    assert names_by_type == PROVIDER_DISPLAY_NAMES


# --- AC2: replacement works for every canonical type + PUT->GET round-trip ---


@pytest.mark.parametrize("secret_type", list(CANONICAL_SECRET_TYPES))
def test_replace_succeeds_for_every_canonical_type(
    secrets_client: TestClient, secret_type: str
) -> None:
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{secret_type}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "a-valid-key-for-any-provider"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["secret_type"] == secret_type
    assert body["configured"] is True
    assert _read_secret(secrets_client, user, secret_type) == "a-valid-key-for-any-provider"


def test_replace_then_status_reflects_configured_state(secrets_client: TestClient) -> None:
    """End-to-end contract: after a replacement the status endpoint reports it configured."""
    user = _create_user(secrets_client, "user@example.com")

    put_response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_GEMINI}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "gemini-fresh-key-001"},
    )
    assert put_response.status_code == 200

    status_response = secrets_client.get(
        "/api/secrets/status", headers=_auth_headers(secrets_client, user)
    )
    assert status_response.status_code == 200
    entry = next(e for e in status_response.json() if e["secret_type"] == SECRET_TYPE_GEMINI)
    assert entry["configured"] is True
    assert entry["status"] == "configured"
    assert entry["validation_state"] == "configured"
    assert entry["last_updated"] is not None


def test_replace_accepts_value_at_minimum_length_boundary(secrets_client: TestClient) -> None:
    """Boundary value at the API layer: exactly ``MIN_SECRET_LENGTH`` chars is accepted."""
    user = _create_user(secrets_client, "user@example.com")
    boundary_value = "k" * MIN_SECRET_LENGTH

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": boundary_value},
    )

    assert response.status_code == 200
    assert _read_secret(secrets_client, user, SECRET_TYPE_CLAUDE) == boundary_value


def test_replace_preserves_internal_whitespace_trimming_only_edges(
    secrets_client: TestClient,
) -> None:
    """Only leading/trailing whitespace is stripped; internal spacing is preserved."""
    user = _create_user(secrets_client, "user@example.com")

    response = secrets_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(secrets_client, user),
        json={"value": "  key with inner spaces 123  "},
    )

    assert response.status_code == 200
    assert _read_secret(secrets_client, user, SECRET_TYPE_CLAUDE) == "key with inner spaces 123"
