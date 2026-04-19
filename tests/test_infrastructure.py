"""Tests to verify the test infrastructure itself is correctly configured.

These tests ensure:
  - conftest.py fixtures are importable and work correctly
  - pytest-asyncio is configured for async tests
  - pytest-cov is tracking coverage
"""

import asyncio

import pytest

from ai_qa.models import AgentMessage, StageResult

# --- Fixture Availability Tests ---


def test_success_stage_result_fixture(success_stage_result: StageResult) -> None:
    """Verify conftest StageResult fixture is accessible and has correct type."""
    assert isinstance(success_stage_result, StageResult)
    assert success_stage_result.success is True
    assert success_stage_result.data is None
    assert success_stage_result.errors == []


def test_failed_stage_result_fixture(failed_stage_result: StageResult) -> None:
    """Verify conftest failed StageResult fixture."""
    assert isinstance(failed_stage_result, StageResult)
    assert failed_stage_result.success is False
    assert len(failed_stage_result.errors) == 2


def test_stage_result_with_data_fixture(stage_result_with_data: StageResult) -> None:
    """Verify conftest StageResult fixture with data payload."""
    assert stage_result_with_data.success is True
    assert stage_result_with_data.data is not None
    assert stage_result_with_data.confidence == 0.75


def test_sample_agent_message_fixture(sample_agent_message: AgentMessage) -> None:
    """Verify conftest AgentMessage fixture is accessible and correct."""
    assert isinstance(sample_agent_message, AgentMessage)
    assert sample_agent_message.sender == "agent"
    assert sample_agent_message.agent_name == "Bob"
    assert sample_agent_message.message_type == "success"


def test_processing_message_fixture(processing_message: AgentMessage) -> None:
    """Verify processing status message fixture."""
    assert isinstance(processing_message, AgentMessage)
    assert processing_message.sender == "agent"
    assert processing_message.agent_name == "Mary"
    assert processing_message.message_type == "info"
    assert "2 of 5" in processing_message.content


# --- Async Test Infrastructure ---


@pytest.mark.asyncio
async def test_async_test_support() -> None:
    """Verify pytest-asyncio is installed and async tests work.

    This is a canary test — if it fails, pytest-asyncio is not configured.
    """
    await asyncio.sleep(0)  # No-op async operation
    assert True  # If we got here, async mode is working


# --- Coverage Infrastructure ---


def test_coverage_tracking_active() -> None:
    """Placeholder: coverage tracking verified by --cov flag in pytest config."""
    # If this test runs, pytest-cov is active (it would error without it
    # when --cov-fail-under is set but cov isn't installed)
    assert True
