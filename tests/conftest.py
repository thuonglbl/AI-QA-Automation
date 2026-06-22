"""Shared test fixtures for ai-qa-automation test suite.

Fixtures defined here are automatically available to all tests without explicit imports.
Use this file for:
  - Test data factories (minimal, valid model instances)
  - Mock objects for external dependencies (LLM, MCP server, browser)
  - Common setup/teardown logic

Scope guidelines:
  - "function" scope (default): stateful objects that need reset per test
  - "session" scope: expensive setup done once (e.g., loading config from env)
"""

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_qa.db.models import User
from ai_qa.models import AgentMessage, StageResult
from ai_qa.pipelines.context import PipelineContext

# --- Cross-test isolation of process-global mutable state -------------------


@pytest.fixture(autouse=True)
def _reset_shared_module_globals() -> Generator[None]:
    """Reset module-level mutable registries between tests (per-test isolation).

    Several modules keep process-global dicts that accumulate across the suite and
    were not consistently torn down, so a test could observe state left by an
    earlier one depending on collection order:

    * ``ai_qa.api.websocket.active_connections`` — populated whenever a test opens a
      real WebSocket. A connection that is not cleanly disconnected lingers and is
      then iterated by the ``broadcast_*`` helpers in *later* tests (e.g. the
      artifact-create path calls ``broadcast_artifact_change``), making those tests
      depend on which WebSocket tests ran before them.
    * ``ai_qa.api.routes._user_agents`` / ``_project_user_agents`` — per-user and
      per-(user, project) agent caches that only grow as tests drive the pipeline.

    Clearing them around every test makes each test independent of ordering. Cleared
    on both entry and exit so a test starts clean regardless of who ran before it and
    leaves nothing behind. ``_active_agents`` is left alone: it is bounded (steps 1-5)
    and re-registered by every ``create_app`` call, and some tests seed it directly.
    """

    def _clear() -> None:
        from ai_qa.api import routes, websocket

        websocket.active_connections.clear()
        routes._user_agents.clear()
        routes._project_user_agents.clear()

    _clear()
    yield
    _clear()


# --- Context Fixtures ---


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    user = User(id="user-123", email="test@example.com")

    def mock_db_get(model, ident, **kwargs):
        from ai_qa.db.models import User
        from ai_qa.threads.models import Thread

        if model is User:
            return user
        if model is Thread:
            thread = Thread(
                id=ident,
                provider_name="claude",
                provider_base_url="",
                agent_configs={"bob": {"model": "claude-sonnet"}},
            )
            return thread
        from unittest.mock import DEFAULT

        return DEFAULT

    db.get.side_effect = mock_db_get
    # Default scalar to a configured UserSecret mock so get_secret_status returns
    # configured=True for the happy-path gate in BobAgent._check_preconditions.
    # Individual tests that need configured=False can override db.scalar.return_value.
    db.scalar.return_value = MagicMock(configured=True, updated_at=None)
    return db


@pytest.fixture
def mock_project_context(mock_db: MagicMock, tmp_path: Path) -> MagicMock:
    context = MagicMock(spec=PipelineContext)
    context.user_id = "user-123"
    context.user_email = "test@example.com"
    context.artifact_service.db = mock_db
    return context


# --- StageResult Fixtures ---


@pytest.fixture
def success_stage_result() -> StageResult:
    """Minimal valid StageResult with success=True."""
    return StageResult(success=True)


@pytest.fixture
def failed_stage_result() -> StageResult:
    """StageResult representing a failed pipeline stage."""
    return StageResult(
        success=False,
        errors=["Connection timeout", "Retry limit exceeded"],
        warnings=[],
    )


@pytest.fixture
def stage_result_with_data() -> StageResult:
    """StageResult with realistic data payload."""
    return StageResult(
        success=True,
        data={"requirements": ["Login with valid credentials", "Logout clears session"]},
        warnings=["Low confidence on requirement 2"],
        confidence=0.75,
    )


# --- AgentMessage Fixtures ---


@pytest.fixture
def sample_agent_message() -> AgentMessage:
    """Minimal valid AgentMessage from agent 'Bob'."""
    return AgentMessage(
        sender="agent",
        agent_name="Bob",
        content="Extracted 3 requirements from Confluence",
        timestamp=datetime(2026, 4, 10, 9, 0, 0, tzinfo=UTC),
        messageType="success",
    )


@pytest.fixture
def processing_message() -> AgentMessage:
    """AgentMessage simulating a processing status update."""
    return AgentMessage(
        sender="agent",
        agent_name="Mary",
        content="Generating test case 2 of 5...",
        timestamp=datetime(2026, 4, 10, 9, 30, 0, tzinfo=UTC),
        messageType="info",
    )
