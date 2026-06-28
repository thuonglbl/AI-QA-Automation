"""Extended tests for FastAPI REST endpoints to cover agent execution logic."""

import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.api.routes import _active_agents, register_agent
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.models import StageResult
from ai_qa.threads.models import Thread


class DummyAgent(BaseAgent):
    def __init__(self, step_number: int = 1, name: str = "DummyAgent") -> None:
        super().__init__(step_number=step_number, name=name, color="blue", step_title="Dummy")
        self.handle_start = AsyncMock()  # type: ignore[method-assign]
        self.handle_approve = AsyncMock()  # type: ignore[method-assign]
        self.handle_reject = AsyncMock()  # type: ignore[method-assign]
        self.handle_continue = AsyncMock()
        self.handle_navigate = AsyncMock()
        self.get_state = MagicMock(return_value=AgentState.REVIEW_REQUEST)

    async def process(self, input_data: dict[str, Any], feedback: str | None = None) -> StageResult:
        return StageResult(success=True)


@pytest.fixture
def dummy_agent() -> Generator[DummyAgent]:
    agent = DummyAgent(step_number=1)
    original_agents = dict(_active_agents)
    register_agent(agent)
    yield agent
    _active_agents.clear()
    _active_agents.update(original_agents)


@pytest.fixture
def extended_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    client = TestClient(app)

    settings = app.state.settings
    session_manager = SessionManager(settings)

    # Create user in DB so authentication succeeds
    session = session_factory()
    user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    thread_id = uuid.UUID("11111111-1111-1111-1111-111111111111")

    user = User(
        id=user_id,
        email="test@example.com",
        display_name="Test User",
        role="standard",
        is_active=True,
    )
    session.add(user)

    thread = Thread(id=thread_id, user_id=user_id)
    session.add(thread)
    session.commit()
    session.close()

    auth_session = session_manager.create_session(
        {
            "user_id": str(user_id),
            "email": "test@example.com",
            "name": "Test User",
            "is_active": True,
        }
    )
    token = session_manager.encode_session(auth_session)
    client.cookies.set(settings.session_cookie_name, token)

    yield client
    app.dependency_overrides.clear()
    engine.dispose()


def test_start_calls_agent(extended_client: TestClient, dummy_agent: DummyAgent) -> None:
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        response = extended_client.post(
            "/api/start",
            json={
                "step": 1,
                "thread_id": "11111111-1111-1111-1111-111111111111",
                "input_data": {"test": "data"},
            },
        )
        assert response.status_code == 200
        dummy_agent.handle_start.assert_called_once()  # type: ignore[attr-defined]


def test_approve_calls_agent(extended_client: TestClient, dummy_agent: DummyAgent) -> None:
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        response = extended_client.post(
            "/api/approve", json={"step": 1, "thread_id": "11111111-1111-1111-1111-111111111111"}
        )
        assert response.status_code == 200
        dummy_agent.handle_approve.assert_called_once()  # type: ignore[attr-defined]


def test_reject_calls_agent(extended_client: TestClient, dummy_agent: DummyAgent) -> None:
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        response = extended_client.post(
            "/api/reject",
            json={
                "step": 1,
                "thread_id": "11111111-1111-1111-1111-111111111111",
                "feedback": "wrong",
            },
        )
        assert response.status_code == 200
        dummy_agent.handle_reject.assert_called_once()  # type: ignore[attr-defined]


def test_continue_calls_agent(extended_client: TestClient, dummy_agent: DummyAgent) -> None:
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        response = extended_client.post(
            "/api/continue",
            json={"from_step": 1, "thread_id": "11111111-1111-1111-1111-111111111111"},
        )
        assert response.status_code == 200
        assert response.json()["current_step"] == 2


def test_navigate_calls_agent(extended_client: TestClient, dummy_agent: DummyAgent) -> None:
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        response = extended_client.post(
            "/api/navigate",
            json={
                "step": 1,
                "thread_id": "11111111-1111-1111-1111-111111111111",
                "direction": "next",
                "current_index": 0,
            },
        )
        assert response.status_code == 200
        dummy_agent.handle_navigate.assert_called_once()


def test_agent_start_exception(extended_client: TestClient, dummy_agent: DummyAgent) -> None:
    dummy_agent.handle_start.side_effect = RuntimeError("Agent Error")  # type: ignore[attr-defined]
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        mock_context.return_value.run_id = str(uuid.uuid4())

        with patch("ai_qa.api.routes._mark_context_run_failed") as mock_failed:
            with pytest.raises(RuntimeError, match="Agent Error"):
                extended_client.post(
                    "/api/start",
                    json={
                        "step": 1,
                        "thread_id": "11111111-1111-1111-1111-111111111111",
                        "input_data": {"test": "data"},
                    },
                )
            mock_failed.assert_called_once()


# ---------------------------------------------------------------------------
# Story 7.6: Membership removal access enforcement (pipeline/WebSocket path)
# ---------------------------------------------------------------------------


@pytest.fixture
def removed_member_client() -> Generator[tuple[TestClient, str]]:
    """Client whose user owns a thread bound to a project they do NOT belong to."""
    from ai_qa.db.models import Project

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    client = TestClient(app)

    settings = app.state.settings
    session_manager = SessionManager(settings)

    user_id = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
    project_id = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
    thread_id = uuid.UUID("00000000-0000-0000-0000-0000000000cc")

    session = session_factory()
    session.add(
        User(
            id=user_id,
            email="removed@example.com",
            display_name="Removed User",
            role="standard",
            is_active=True,
        )
    )
    session.add(Project(id=project_id, name="Bound Project", description="desc"))
    # Thread bound to the project, but NO ProjectMembership row for the user.
    session.add(Thread(id=thread_id, user_id=user_id, project_id=project_id))
    session.commit()
    session.close()

    auth_session = session_manager.create_session(
        {
            "user_id": str(user_id),
            "email": "removed@example.com",
            "name": "Removed User",
            "is_active": True,
        }
    )
    token = session_manager.encode_session(auth_session)
    client.cookies.set(settings.session_cookie_name, token)

    yield client, str(thread_id)
    app.dependency_overrides.clear()
    engine.dispose()


def test_pipeline_start_denied_for_removed_member(
    removed_member_client: tuple[TestClient, str], dummy_agent: DummyAgent
) -> None:
    """Driving a project-bound thread without membership returns a generic 404.

    Exercises the real _build_pipeline_context (no mock) so the pipeline/WebSocket
    dispatch path is regression-covered: access is denied before the agent runs.
    """
    client, thread_id = removed_member_client

    response = client.post(
        "/api/start",
        json={"step": 1, "thread_id": thread_id, "input_data": {"test": "data"}},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Resource not found"}
    dummy_agent.handle_start.assert_not_called()  # type: ignore[attr-defined]
