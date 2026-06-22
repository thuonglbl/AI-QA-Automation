"""Shared fixtures for admin/project/membership API tests.

These tests drive the real FastAPI app (built via ``create_app``) through a
synchronous ``TestClient`` — matching the established pattern in
``test_admin_rbac_api.py`` / ``test_admin_e2e_api.py``. The database is an
in-memory SQLite engine shared (via ``StaticPool``) between the test's
``db_session`` and the request-time session yielded by the dependency override,
so rows seeded by fixtures are visible to the endpoints under test.

Auth uses ``Authorization: Bearer <jwt>`` headers; the ``AuthMiddleware`` reads
the cookie first and falls back to this header.
"""

import uuid
from collections.abc import Callable, Generator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User


@pytest.fixture
def _engine() -> Generator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def _session_factory(_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=_engine, expire_on_commit=False)


@pytest.fixture
def db_session(_session_factory: sessionmaker[Session]) -> Generator[Session]:
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(_session_factory: sessionmaker[Session]) -> Generator[TestClient]:
    def override_get_db_session() -> Generator[Session]:
        session = _session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _make_user(session: Session, email: str, role: str, *, active: bool = True) -> User:
    user = User(
        email=email,
        display_name=email.split("@")[0],
        password_hash=hash_password("super-secret"),
        role=role,
        is_active=active,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


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
    return session_manager.encode_session(session)


@pytest.fixture
def token_factory(client: TestClient) -> Callable[[User], str]:
    """Return a helper that mints a bearer token for any User (e.g. project_admins)."""

    def _factory(user: User) -> str:
        return _token(client, user)

    return _factory


@pytest.fixture
def user_factory(db_session: Session) -> Callable[..., User]:
    def _factory(
        email: str | None = None, role: str = STANDARD_ROLE, *, active: bool = True
    ) -> User:
        resolved_email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        return _make_user(db_session, resolved_email, role, active=active)

    return _factory


@pytest.fixture
def admin_token(client: TestClient, db_session: Session) -> str:
    admin = _make_user(db_session, "admin@example.com", ADMIN_ROLE)
    return _token(client, admin)


@pytest.fixture
def user_token(client: TestClient, db_session: Session) -> str:
    standard = _make_user(db_session, "standard@example.com", STANDARD_ROLE)
    return _token(client, standard)


@pytest.fixture
def db_user(user_factory: Callable[..., User]) -> User:
    return user_factory("member@example.com")


@pytest.fixture
def db_user2(user_factory: Callable[..., User]) -> User:
    return user_factory("member2@example.com")


@pytest.fixture
def db_project(db_session: Session) -> Project:
    project = Project(
        name="Seed Project",
        description="Seed project for API tests",
        confluence_base_url="https://confluence.example.com",
        enabled_providers=["openai"],
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture
def db_membership(db_session: Session, db_project: Project, db_user: User) -> ProjectMembership:
    membership = ProjectMembership(project_id=db_project.id, user_id=db_user.id, role="member")
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


@pytest.fixture
def fake_uuid() -> uuid.UUID:
    return uuid.uuid4()
