"""Tests for project-scoped WebSocket pipeline dispatch."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.agents.base import BaseAgent
from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.api.routes import _active_agents, _project_user_agents, _user_agents
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User
from ai_qa.models import StageResult
from ai_qa.threads.models import AgentRun, Thread


class RecordingAgent(BaseAgent):
    """Agent that records project context received from WebSocket dispatch."""

    def __init__(self, workspace_dir: Path | None = None) -> None:
        super().__init__(
            name="Bob",
            color="#fff",
            step_number=2,
            step_title="Record context",
            workspace_dir=workspace_dir,
        )
        self.seen_input: dict[str, object] | None = None

    async def process(
        self, input_data: dict[str, object], feedback: str | None = None
    ) -> StageResult:
        self.seen_input = input_data
        return StageResult(success=True)


@pytest.fixture
def ws_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                User.__table__,
                Project.__table__,
                ProjectMembership.__table__,
                Thread.__table__,
                AgentRun.__table__,
            ],
        ),
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
    _active_agents.clear()
    _user_agents.clear()
    _project_user_agents.clear()
    _active_agents[2] = RecordingAgent()
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
    _active_agents.clear()
    _user_agents.clear()
    _project_user_agents.clear()


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    return app.dependency_overrides[get_db_session_dependency]()


def _create_user(client: TestClient, email: str, role: str) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
            role=role,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _create_project(client: TestClient, creator: User | None = None) -> Project:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        project = Project(name="Scoped", created_by_user_id=creator.id if creator else None)
        session.add(project)
        session.commit()
        session.refresh(project)
        session.expunge(project)
        return project
    finally:
        session_gen.close()


def _add_membership(client: TestClient, project: Project, user: User) -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="member"))
        session.commit()
    finally:
        session_gen.close()


def _create_thread(client: TestClient, project: Project, user: User) -> Thread:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        thread = Thread(project_id=project.id, user_id=user.id)
        session.add(thread)
        session.commit()
        session.refresh(thread)
        session.expunge(thread)
        return thread
    finally:
        session_gen.close()


def _auth_cookie(client: TestClient, user: User) -> dict[str, str]:
    app = cast(FastAPI, client.app)
    manager = SessionManager(app.state.settings)
    session = manager.create_session(
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
    token = manager.encode_session(session)
    cookie_name = app.state.settings.session_cookie_name
    # Set cookie on client instance (not per-request) to avoid Starlette deprecation
    client.cookies.set(cookie_name, token)
    return {cookie_name: token}


def test_websocket_start_requires_project_id_for_authenticated_user(
    ws_client: TestClient,
) -> None:
    user = _create_user(ws_client, "member@example.com", STANDARD_ROLE)
    _auth_cookie(ws_client, user)  # sets cookie on client

    with ws_client.websocket_connect("/ws") as websocket:
        auth_status = websocket.receive_json()
        assert auth_status["authenticated"] is True

        websocket.send_json({"type": "start", "step": 2})
        error = websocket.receive_json()

    assert error["type"] == "error"
    assert "project_id or thread_id is required" in error["message"]


def test_websocket_denies_non_member_and_allows_member_message_project(
    ws_client: TestClient,
) -> None:
    member = _create_user(ws_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(ws_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(ws_client)
    _add_membership(ws_client, project, member)

    thread = _create_thread(ws_client, project, member)

    _auth_cookie(ws_client, outsider)  # sets outsider cookie on client
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json(
            {"type": "start", "step": 2, "projectId": str(project.id), "threadId": str(thread.id)}
        )
        denied = websocket.receive_json()

    assert denied["type"] == "error"
    assert "Forbidden thread access" in denied["message"]

    _auth_cookie(ws_client, member)  # sets member cookie on client
    with ws_client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "start",
                "step": 2,
                "projectId": str(project.id),
                "threadId": str(thread.id),
                "inputData": {"url": "https://example.com"},
            }
        )

    agent = _project_user_agents[(str(member.id), str(project.id), 2)]
    assert agent.project_context is not None
    assert agent.project_context.project_id == project.id
    assert agent.project_context.user_id == member.id
    assert agent.project_context.agent_run_id is not None
    assert isinstance(agent, RecordingAgent)
    assert agent.seen_input == {"url": "https://example.com"}


def test_websocket_allows_admin_with_query_project_id(ws_client: TestClient) -> None:
    admin = _create_user(ws_client, "admin@example.com", ADMIN_ROLE)
    project = _create_project(ws_client, admin)

    thread = _create_thread(ws_client, project, admin)

    _auth_cookie(ws_client, admin)  # sets admin cookie on client
    with ws_client.websocket_connect(
        f"/ws?projectId={project.id}&threadId={thread.id}"
    ) as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "start", "step": 2})

    agent = _project_user_agents[(str(admin.id), str(project.id), 2)]
    assert agent.project_context is not None
    assert agent.project_context.project_id == project.id
