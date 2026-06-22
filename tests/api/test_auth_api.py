"""API tests for local DB-backed authentication routes."""

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
from ai_qa.auth.service import register_user
from ai_qa.db.base import Base
from ai_qa.db.models import User


@pytest.fixture
def auth_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=cast(list[Table], [User.__table__]))
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


def _seed_standard_user(client: TestClient, email: str, name: str, password: str) -> User:
    """Seed a standard user directly via the auth service.

    Public self-service registration is locked down (Story 8.7), so tests
    bootstrap accounts through the domain service instead of POST /auth/register.
    """
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    session = next(db_override())
    try:
        return register_user(session, email, name, password)
    finally:
        session.close()


def test_public_registration_route_is_removed(auth_client: TestClient) -> None:
    """Story 8.7 AC1: the public self-service registration route must not exist."""
    app = cast(FastAPI, auth_client.app)
    register_routes = [
        route for route in app.routes if getattr(route, "path", None) == "/auth/register"
    ]
    assert register_routes == []


def test_unauthenticated_registration_attempt_creates_no_account(
    auth_client: TestClient,
) -> None:
    """Story 8.7 AC1/AC3: an unauthenticated POST /auth/register is rejected and
    creates no user account, without leaking whether the email exists."""
    response = auth_client.post(
        "/auth/register",
        json={
            "email": "intruder@example.com",
            "name": "Intruder",
            "password": "super-secret",
        },
        follow_redirects=False,
    )

    # The route is removed and the path is no longer whitelisted, so the auth
    # middleware blocks the request before any handler runs.
    assert response.status_code in {307, 401, 403, 404}
    assert "password_hash" not in response.text

    app = cast(FastAPI, auth_client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    session = next(db_override())
    try:
        assert session.query(User).filter_by(email="intruder@example.com").first() is None
    finally:
        session.close()


def test_login_and_me_flow(auth_client: TestClient) -> None:
    _seed_standard_user(auth_client, "Person@Example.COM", "Person One", "super-secret")

    login_response = auth_client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "super-secret"},
    )

    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["token_type"] == "bearer"
    assert login_data["access_token"]

    me_response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )

    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == "person@example.com"
    assert me_data["display_name"] == "Person One"
    assert me_data["role"] == "standard"
    assert me_data["is_active"] is True
    assert me_data["timezone"] == "UTC"  # surfaced so the FE can localize timestamps
    assert "password_hash" not in me_data


def test_invalid_login_is_rejected_with_safe_message(auth_client: TestClient) -> None:
    _seed_standard_user(auth_client, "person@example.com", "Person One", "super-secret")

    login_response = auth_client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "wrong-secret"},
    )
    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"


def test_me_requires_authentication(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_rejects_deactivated_user_after_token_issuance(auth_client: TestClient) -> None:
    _seed_standard_user(auth_client, "person@example.com", "Person One", "super-secret")
    login_response = auth_client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "super-secret"},
    )
    token = login_response.json()["access_token"]

    app = cast(FastAPI, auth_client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    session = next(db_override())
    try:
        user = session.query(User).filter_by(email="person@example.com").one()
        user.is_active = False
        session.commit()
    finally:
        session.close()

    me_response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me_response.status_code == 401
    assert me_response.json()["detail"] == "Not authenticated"


def test_auth_status_returns_profile_with_id_when_authenticated(auth_client: TestClient) -> None:
    """Story 7.7 regression: /auth/status must return `id` so the page-reload
    bootstrap (per-project starter threads) has `user.id` to work with."""
    _seed_standard_user(auth_client, "person@example.com", "Person One", "super-secret")
    login_response = auth_client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "super-secret"},
    )
    token = login_response.json()["access_token"]

    status_response = auth_client.get(
        "/auth/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert status_response.status_code == 200
    data = status_response.json()
    assert data["authenticated"] is True
    assert data["id"]
    assert data["email"] == "person@example.com"
    assert data["name"] == "Person One"
    assert data["role"] == "standard"
    assert "password_hash" not in data


def test_auth_status_reports_unauthenticated_without_session(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/status")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
