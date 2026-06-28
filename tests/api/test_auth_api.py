"""API tests for auth routes."""

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
from ai_qa.config import AppSettings
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


def _seed_standard_user(client: TestClient, email: str, name: str) -> User:
    """Seed a standard user."""
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    session = next(db_override())
    try:
        user = User(email=email.lower(), display_name=name)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user
    finally:
        session.close()


def _get_token(client: TestClient, user: User) -> str:
    # The actual dependencies use AppSettings, so we can instantiate SessionManager directly
    settings = AppSettings()
    manager = SessionManager(settings)

    user_data = {
        "email": user.email,
        "name": user.display_name,
        "user_id": str(user.id),
        "role": user.role,
        "is_active": user.is_active,
    }

    session = manager.create_session(user_data)
    return manager.encode_session(session)


def test_me_requires_authentication(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_returns_profile_when_authenticated(auth_client: TestClient) -> None:
    user = _seed_standard_user(auth_client, "Person@Example.COM", "Person One")
    token = _get_token(auth_client, user)

    me_response = auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200
    me_data = me_response.json()
    assert me_data["email"] == "person@example.com"
    assert me_data["display_name"] == "Person One"
    assert me_data["role"] == "standard"
    assert me_data["is_active"] is True


def test_auth_status_returns_profile_with_id_when_authenticated(auth_client: TestClient) -> None:
    user = _seed_standard_user(auth_client, "person@example.com", "Person One")
    token = _get_token(auth_client, user)

    status_response = auth_client.get(
        "/auth/status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert status_response.status_code == 200
    data = status_response.json()
    assert data["authenticated"] is True
    assert data["id"] == str(user.id)
    assert data["email"] == "person@example.com"
    assert data["name"] == "Person One"
    assert data["role"] == "standard"


def test_auth_status_reports_unauthenticated_without_session(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/status")

    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
