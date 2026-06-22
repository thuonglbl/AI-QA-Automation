"""Extended tests for FastAPI REST endpoints covering skip and health check."""

import uuid
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.agents.base import BaseAgent
from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.api.routes import _active_agents, register_agent
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.models import StageResult
from ai_qa.threads.models import Thread


class DummySkipAgent(BaseAgent):
    def __init__(self, step_number: int = 1, name: str = "DummySkipAgent") -> None:
        super().__init__(step_number=step_number, name=name, color="blue", step_title="Dummy")
        self.handle_skip = AsyncMock()  # type: ignore[method-assign]

    async def process(self, input_data: dict[str, Any], feedback: str | None = None) -> StageResult:
        return StageResult(success=True)


@pytest.fixture
def dummy_skip_agent() -> Generator[DummySkipAgent]:
    agent = DummySkipAgent(step_number=1)
    original_agents = dict(_active_agents)
    register_agent(agent)
    yield agent
    _active_agents.clear()
    _active_agents.update(original_agents)


@pytest.fixture
def skip_client() -> Generator[TestClient]:
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
        password_hash="hash",
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


def test_skip_calls_agent(skip_client: TestClient, dummy_skip_agent: DummySkipAgent) -> None:
    with patch("ai_qa.api.routes._build_pipeline_context") as mock_context:
        mock_context.return_value = MagicMock()
        mock_context.return_value.project_id = None
        mock_context.return_value.user_email = None
        response = skip_client.post(
            "/api/skip",
            json={
                "step": 1,
                "thread_id": "11111111-1111-1111-1111-111111111111",
            },
        )
        assert response.status_code == 200
        dummy_skip_agent.handle_skip.assert_called_once()  # type: ignore[attr-defined]


def test_health_check(skip_client: TestClient) -> None:
    response = skip_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"healthy", "degraded"}
