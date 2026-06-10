"""Tests for project-scoped pipeline context propagation."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import cast
from uuid import UUID

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


class RecordingAgent(BaseAgent):  # type: ignore[misc]
    """Agent that records project context received from API dispatch."""

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


class FailingAgent(RecordingAgent):
    """Agent that fails during processing to verify run failure recording."""

    async def process(
        self, input_data: dict[str, object], feedback: str | None = None
    ) -> StageResult:
        raise RuntimeError("boom")


@pytest.fixture
def pipeline_client() -> Generator[TestClient]:
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
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()
    _active_agents.clear()
    _user_agents.clear()
    _project_user_agents.clear()


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    return cast(Generator[Session], app.dependency_overrides[get_db_session_dependency]())


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


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
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
    return {"Authorization": f"Bearer {manager.encode_session(session)}"}


def test_project_start_requires_authenticated_project_id(pipeline_client: TestClient) -> None:
    user = _create_user(pipeline_client, "member@example.com", STANDARD_ROLE)

    missing = pipeline_client.post(
        "/api/start", json={"step": 2}, headers=_auth_headers(pipeline_client, user)
    )
    unauthenticated = pipeline_client.post(
        "/api/start", json={"step": 2, "project_id": str(UUID(int=1))}
    )

    assert missing.status_code == 422
    assert unauthenticated.status_code == 401


def test_project_start_denies_non_member_and_allows_member(
    pipeline_client: TestClient,
) -> None:
    member = _create_user(pipeline_client, "member@example.com", STANDARD_ROLE)
    outsider = _create_user(pipeline_client, "outsider@example.com", STANDARD_ROLE)
    project = _create_project(pipeline_client)
    _add_membership(pipeline_client, project, member)

    thread = _create_thread(pipeline_client, project, member)

    outsider_thread = _create_thread(pipeline_client, project, outsider)

    denied = pipeline_client.post(
        "/api/start",
        json={"step": 2, "project_id": str(project.id), "thread_id": str(outsider_thread.id)},
        headers=_auth_headers(pipeline_client, outsider),
    )
    allowed = pipeline_client.post(
        "/api/start",
        json={
            "step": 2,
            "project_id": str(project.id),
            "thread_id": str(thread.id),
            "input_data": {"url": "x"},
        },
        headers=_auth_headers(pipeline_client, member),
    )

    assert denied.status_code == 404
    assert allowed.status_code == 200
    assert allowed.json()["status"] == "review_request"
    agent = _project_user_agents[(str(member.id), str(project.id), 2)]
    assert agent.project_context is not None
    assert agent.project_context.project_id == project.id
    assert agent.project_context.user_id == member.id
    assert agent.project_context.user_email == member.email
    assert agent.project_context.agent_run_id is not None

    session_gen = _session_from_override(pipeline_client)
    session = next(session_gen)
    try:
        agent_run = session.get(AgentRun, agent.project_context.agent_run_id)
        assert agent_run is not None
        assert agent_run.thread_id == agent.project_context.thread_id
        assert agent_run.status == "running"
        assert agent_run.created_at is not None
    finally:
        session_gen.close()


def test_project_start_allows_admin_without_membership(pipeline_client: TestClient) -> None:
    admin = _create_user(pipeline_client, "admin@example.com", ADMIN_ROLE)
    project = _create_project(pipeline_client, admin)

    thread = _create_thread(pipeline_client, project, admin)

    response = pipeline_client.post(
        "/api/start",
        json={"step": 2, "project_id": str(project.id), "thread_id": str(thread.id)},
        headers=_auth_headers(pipeline_client, admin),
    )

    assert response.status_code == 200
    assert _project_user_agents[(str(admin.id), str(project.id), 2)].project_context is not None


def test_project_run_marked_completed_when_agent_reaches_done(
    pipeline_client: TestClient,
) -> None:
    member = _create_user(pipeline_client, "done@example.com", STANDARD_ROLE)
    project = _create_project(pipeline_client)
    _add_membership(pipeline_client, project, member)

    thread = _create_thread(pipeline_client, project, member)

    start = pipeline_client.post(
        "/api/start",
        json={"step": 2, "project_id": str(project.id), "thread_id": str(thread.id)},
        headers=_auth_headers(pipeline_client, member),
    )
    assert start.status_code == 200
    agent = _project_user_agents[(str(member.id), str(project.id), 2)]
    assert agent.project_context is not None
    agent_run_id = agent.project_context.agent_run_id

    approve = pipeline_client.post(
        "/api/approve",
        json={"step": 2, "project_id": str(project.id), "thread_id": str(thread.id)},
        headers=_auth_headers(pipeline_client, member),
    )

    assert approve.status_code == 200
    session_gen = _session_from_override(pipeline_client)
    session = next(session_gen)
    try:
        agent_run = session.get(AgentRun, agent_run_id)
        assert agent_run is not None
        assert agent_run.status == "completed"
        assert agent_run.updated_at is not None
        assert agent_run.execution_metadata is not None
        assert agent_run.execution_metadata["completed_step"] == 2
        assert agent_run.execution_metadata["completed_action"] == "approve"
    finally:
        session_gen.close()


def test_project_run_marked_failed_when_agent_raises(pipeline_client: TestClient) -> None:
    _active_agents[2] = FailingAgent()
    member = _create_user(pipeline_client, "fail@example.com", STANDARD_ROLE)
    project = _create_project(pipeline_client)
    _add_membership(pipeline_client, project, member)

    thread = _create_thread(pipeline_client, project, member)

    response = pipeline_client.post(
        "/api/start",
        json={"step": 2, "project_id": str(project.id), "thread_id": str(thread.id)},
        headers=_auth_headers(pipeline_client, member),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "error"
    agent = _project_user_agents[(str(member.id), str(project.id), 2)]
    assert agent.project_context is not None
    session_gen = _session_from_override(pipeline_client)
    session = next(session_gen)
    try:
        agent_run = session.get(AgentRun, agent.project_context.agent_run_id)
        assert agent_run is not None
        assert agent_run.status == "failed"
        assert agent_run.updated_at is not None
        assert agent_run.execution_metadata is not None
        assert agent_run.execution_metadata["failed_step"] == 2
        assert agent_run.execution_metadata["failed_action"] == "start"
        assert "agent" in agent_run.execution_metadata
    finally:
        session_gen.close()
