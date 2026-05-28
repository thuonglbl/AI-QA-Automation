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

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_qa.db.models import User
from ai_qa.models import AgentMessage, StageResult
from ai_qa.pipelines.context import PipelineContext

# --- Context Fixtures ---


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    user = User(id="user-123", email="test@example.com")
    db.get.return_value = user
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
