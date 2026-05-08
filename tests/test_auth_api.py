"""API tests for local DB-backed authentication routes."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.db.base import Base
from ai_qa.db.models import User


@pytest.fixture
def auth_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[User.__table__])
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


def test_register_login_and_me_flow(auth_client: TestClient) -> None:
    register_response = auth_client.post(
        "/auth/register",
        json={
            "email": "Person@Example.COM",
            "name": "Person One",
            "password": "super-secret",
            "role": "admin",
        },
    )

    assert register_response.status_code == 200
    registered_user = register_response.json()["user"]
    assert registered_user["email"] == "person@example.com"
    assert registered_user["role"] == "standard"
    assert "password_hash" not in registered_user

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
    assert "password_hash" not in me_data


def test_duplicate_register_and_invalid_login_are_rejected(auth_client: TestClient) -> None:
    auth_client.post(
        "/auth/register",
        json={"email": "person@example.com", "name": "Person One", "password": "super-secret"},
    )

    duplicate_response = auth_client.post(
        "/auth/register",
        json={"email": "PERSON@example.com", "name": "Other", "password": "other-secret"},
    )
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["detail"] == "Registration could not be completed"

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
    auth_client.post(
        "/auth/register",
        json={"email": "person@example.com", "name": "Person One", "password": "super-secret"},
    )
    login_response = auth_client.post(
        "/auth/login",
        json={"email": "person@example.com", "password": "super-secret"},
    )
    token = login_response.json()["access_token"]

    auth_client.app.dependency_overrides[get_db_session_dependency]
    db_override = auth_client.app.dependency_overrides[get_db_session_dependency]
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
