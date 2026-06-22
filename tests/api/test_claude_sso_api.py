"""API tests for the Claude enterprise SSO login flow (mock IdP).

Covers the mock-mode happy path (start -> authorize page -> callback ->
status), credential storage as the ``claude_sso`` secret, and the per-user /
per-state scoping of the status poll. Fixture scaffold mirrors
``tests/api/test_secrets_api.py`` (in-memory SQLite ``StaticPool``,
``dependency_overrides`` wiring, ``engine.dispose()`` teardown).
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
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.config import AppSettings
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.secrets import SECRET_TYPE_CLAUDE_SSO
from ai_qa.secrets.models import UserSecret
from ai_qa.secrets.service import get_user_secret

ENTERPRISE_KEY = "ent-key-test-12345678"


def _make_client(domain: str = "") -> tuple[TestClient, sessionmaker[Session]]:
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

    settings = AppSettings().model_copy(
        update={
            "claude_sso_authorize_url": "",  # mock IdP mode
            "claude_sso_allowed_email_domain": domain,
            "claude_sso_enterprise_api_key": ENTERPRISE_KEY,
        }
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    client = TestClient(app)
    client.__enter__()
    return client, session_factory


@pytest.fixture
def sso_client() -> Generator[TestClient]:
    client, _ = _make_client()
    try:
        yield client
    finally:
        app = cast(FastAPI, client.app)
        client.__exit__(None, None, None)
        app.dependency_overrides.clear()


def _create_user(client: TestClient, email: str) -> User:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    session_gen = cast(Generator[Session], db_override())
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
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


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
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
    return {"Authorization": f"Bearer {session_manager.encode_session(session)}"}


def _read_secret(client: TestClient, user: User, secret_type: str) -> str | None:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    session_gen = cast(Generator[Session], db_override())
    session = next(session_gen)
    try:
        return get_user_secret(session, user.id, secret_type)
    finally:
        session_gen.close()


def _start(client: TestClient, user: User) -> dict[str, str]:
    response = client.post("/api/auth/claude-sso/start", headers=_auth_headers(client, user))
    assert response.status_code == 200, response.text
    return cast(dict[str, str], response.json())


def test_start_returns_relative_mock_authorize_url(sso_client: TestClient) -> None:
    user = _create_user(sso_client, "user@example.com")
    data = _start(sso_client, user)
    assert data["mode"] == "mock"
    assert data["state"]
    # Mock mode returns a ROOT-RELATIVE path so the frontend opens it on its own
    # origin (dev Vite proxy carries the session cookie).
    assert data["authorize_url"].startswith("/api/auth/claude-sso/authorize?state=")


def test_authorize_page_renders_login_form(sso_client: TestClient) -> None:
    user = _create_user(sso_client, "user@example.com")
    data = _start(sso_client, user)
    response = sso_client.get(
        f"/api/auth/claude-sso/authorize?state={data['state']}",
        headers=_auth_headers(sso_client, user),
    )
    assert response.status_code == 200
    body = response.text
    assert 'data-testid="sso-form"' in body
    assert 'data-testid="sso-email"' in body
    assert 'data-testid="sso-password"' in body
    assert data["state"] in body


def test_callback_stores_token_and_status_flips(sso_client: TestClient) -> None:
    user = _create_user(sso_client, "user@example.com")
    data = _start(sso_client, user)
    headers = _auth_headers(sso_client, user)

    # Before login, status is not authenticated.
    pre = sso_client.get(f"/api/auth/claude-sso/status?state={data['state']}", headers=headers)
    assert pre.status_code == 200
    assert pre.json()["authenticated"] is False

    # Submit the mock IdP form.
    cb = sso_client.post(
        "/api/auth/claude-sso/callback",
        headers=headers,
        data={
            "state": data["state"],
            "email": "user@example.com",
            "password": "any-password",
        },
    )
    assert cb.status_code == 200
    assert 'data-testid="sso-success"' in cb.text

    # The enterprise credential is stored as the claude_sso secret (never the password).
    assert _read_secret(sso_client, user, SECRET_TYPE_CLAUDE_SSO) == ENTERPRISE_KEY

    # Status now reports authenticated.
    post = sso_client.get(f"/api/auth/claude-sso/status?state={data['state']}", headers=headers)
    assert post.json()["authenticated"] is True


def test_status_is_scoped_to_the_owning_user(sso_client: TestClient) -> None:
    owner = _create_user(sso_client, "owner@example.com")
    other = _create_user(sso_client, "other@example.com")
    data = _start(sso_client, owner)
    sso_client.post(
        "/api/auth/claude-sso/callback",
        headers=_auth_headers(sso_client, owner),
        data={"state": data["state"], "email": "owner@example.com", "password": "pw123456"},
    )
    # A different user polling the same state never sees it as authenticated.
    resp = sso_client.get(
        f"/api/auth/claude-sso/status?state={data['state']}",
        headers=_auth_headers(sso_client, other),
    )
    assert resp.json()["authenticated"] is False


def test_callback_rejects_unknown_state(sso_client: TestClient) -> None:
    user = _create_user(sso_client, "user@example.com")
    resp = sso_client.post(
        "/api/auth/claude-sso/callback",
        headers=_auth_headers(sso_client, user),
        data={"state": "bogus-state", "email": "user@example.com", "password": "pw123456"},
    )
    assert resp.status_code == 400


def test_callback_enforces_allowed_email_domain() -> None:
    client, _ = _make_client(domain="company.com")
    try:
        user = _create_user(client, "user@example.com")
        data = _start(client, user)
        resp = client.post(
            "/api/auth/claude-sso/callback",
            headers=_auth_headers(client, user),
            data={"state": data["state"], "email": "user@example.com", "password": "pw123456"},
        )
        # Wrong-domain email: the login page re-renders an error, secret not stored.
        assert resp.status_code == 200
        assert 'data-testid="sso-error"' in resp.text
        assert _read_secret(client, user, SECRET_TYPE_CLAUDE_SSO) is None
    finally:
        app = cast(FastAPI, client.app)
        client.__exit__(None, None, None)
        app.dependency_overrides.clear()
