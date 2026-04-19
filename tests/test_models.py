"""Tests for shared Pydantic models (StageResult, AgentMessage)."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from ai_qa.models import AgentMessage, StageResult

# --- StageResult Tests ---


def test_stage_result_success_with_data() -> None:
    """StageResult with success=True and data."""
    result = StageResult(
        success=True,
        data={"test": "output"},
        errors=[],
        warnings=["unused_field"],
        confidence=0.95,
    )
    assert result.success is True
    assert result.data == {"test": "output"}
    assert result.errors == []
    assert result.warnings == ["unused_field"]
    assert result.confidence == 0.95


def test_stage_result_failure_with_errors() -> None:
    """StageResult with success=False and errors."""
    result = StageResult(
        success=False,
        data=None,
        errors=["MCP timeout", "Retry limit exceeded"],
        warnings=[],
        confidence=None,
    )
    assert result.success is False
    assert result.data is None
    assert len(result.errors) == 2
    assert result.confidence is None


def test_stage_result_defaults() -> None:
    """StageResult fields have sensible defaults."""
    result = StageResult(success=True)
    assert result.success is True
    assert result.data is None
    assert result.errors == []
    assert result.warnings == []
    assert result.confidence is None


def test_stage_result_confidence_validation_zero() -> None:
    """Confidence can be 0.0."""
    result = StageResult(success=True, confidence=0.0)
    assert result.confidence == 0.0


def test_stage_result_confidence_validation_one() -> None:
    """Confidence can be 1.0."""
    result = StageResult(success=True, confidence=1.0)
    assert result.confidence == 1.0


def test_stage_result_confidence_validation_none() -> None:
    """Confidence can be None."""
    result = StageResult(success=True, confidence=None)
    assert result.confidence is None


def test_stage_result_confidence_validation_too_high() -> None:
    """Confidence > 1.0 is rejected."""
    with pytest.raises(ValidationError):
        StageResult(success=True, confidence=1.5)


def test_stage_result_confidence_validation_negative() -> None:
    """Confidence < 0.0 is rejected."""
    with pytest.raises(ValidationError):
        StageResult(success=True, confidence=-0.1)


def test_stage_result_success_errors_consistency() -> None:
    """success=True with non-empty errors list is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        StageResult(
            success=True,
            data=None,
            errors=["Something failed"],
            warnings=[],
            confidence=None,
        )
    assert "success=True but errors" in str(exc_info.value)


def test_stage_result_errors_list_max_length() -> None:
    """errors list cannot exceed 100 items."""
    with pytest.raises(ValidationError):
        StageResult(
            success=False,
            errors=["Error"] * 101,  # 101 items, exceeds max_length=100
        )


def test_stage_result_warnings_list_max_length() -> None:
    """warnings list cannot exceed 100 items."""
    with pytest.raises(ValidationError):
        StageResult(
            success=True,
            warnings=["Warning"] * 101,  # 101 items, exceeds max_length=100
        )


def test_stage_result_json_serialization() -> None:
    """StageResult serializes to JSON with snake_case keys."""
    result = StageResult(
        success=True,
        data={"inner_key": "value"},
        errors=[],
        warnings=[],
        confidence=0.85,
    )
    json_str = result.model_dump_json()
    data = json.loads(json_str)

    # Verify snake_case in JSON
    assert "success" in data
    assert "data" in data
    assert "errors" in data
    assert "warnings" in data
    assert "confidence" in data
    assert data["success"] is True
    assert data["confidence"] == 0.85


def test_stage_result_json_deserialization() -> None:
    """StageResult can be reconstructed from JSON."""
    original = StageResult(
        success=True,
        data=["item1", "item2"],
        errors=[],
        warnings=["warning1"],
        confidence=0.72,
    )
    json_str = original.model_dump_json()
    reconstructed = StageResult.model_validate_json(json_str)

    assert reconstructed.success == original.success
    assert reconstructed.data == original.data
    assert reconstructed.warnings == original.warnings
    assert reconstructed.confidence == original.confidence


# --- AgentMessage Tests ---


def test_agent_message_creation() -> None:
    """AgentMessage with all fields."""
    now = datetime(2026, 4, 8, 10, 30, 45, 123456, tzinfo=UTC)
    msg = AgentMessage(
        sender="agent",
        agent_name="Bob",
        content="Parsed 5 requirements from Confluence",
        timestamp=now,
        message_type="info",
    )
    assert msg.sender == "agent"
    assert msg.agent_name == "Bob"
    assert msg.content == "Parsed 5 requirements from Confluence"
    assert msg.timestamp == now
    assert msg.message_type == "info"


def test_agent_message_timestamp_with_datetime() -> None:
    """AgentMessage timestamp can be a datetime object (timezone-aware)."""
    now = datetime.now(UTC)
    msg = AgentMessage(
        sender="agent",
        agent_name="Mary",
        content="Generated 3 test cases",
        timestamp=now,
        message_type="success",
    )
    assert isinstance(msg.timestamp, datetime)
    assert msg.timestamp == now


def test_agent_message_json_serialization_iso8601() -> None:
    """AgentMessage timestamp serializes to ISO 8601 in JSON."""
    msg = AgentMessage(
        sender="agent",
        agent_name="Sarah",
        content="Script generation complete",
        timestamp=datetime(2026, 4, 8, 10, 30, 45, 123456, tzinfo=UTC),
        message_type="success",
    )
    json_str = msg.model_dump_json(by_alias=True)
    data = json.loads(json_str)

    # Timestamp must be ISO 8601 string in JSON
    assert isinstance(data["timestamp"], str)
    assert data["timestamp"] == "2026-04-08T10:30:45.123456+00:00"
    assert "T" in data["timestamp"]  # ISO 8601 format
    # Verify camelCase aliases are used
    assert data["agentName"] == "Sarah"
    assert data["messageType"] == "success"


def test_agent_message_json_deserialization() -> None:
    """AgentMessage can be reconstructed from JSON (string timestamp with timezone)."""
    json_str = (
        '{"sender": "agent", "agentName": "Jack", "content": "3/5 scripts passed", '
        '"timestamp": "2026-04-08T14:22:30.000000+00:00", "messageType": "warning"}'
    )
    msg = AgentMessage.model_validate_json(json_str)

    assert msg.sender == "agent"
    assert msg.agent_name == "Jack"
    assert msg.content == "3/5 scripts passed"
    assert isinstance(msg.timestamp, datetime)
    assert msg.timestamp.year == 2026
    assert msg.message_type == "warning"


def test_agent_message_validation_sender_required() -> None:
    """AgentMessage sender is required."""
    with pytest.raises(ValidationError):
        AgentMessage(
            content="test",
            timestamp=datetime.now(UTC),
            message_type="info",
        )


def test_agent_message_validation_content_required() -> None:
    """AgentMessage content is required."""
    with pytest.raises(ValidationError):
        AgentMessage(
            sender="agent",
            timestamp=datetime.now(UTC),
            message_type="info",
        )


def test_agent_message_validation_message_type_required() -> None:
    """AgentMessage message_type is required."""
    with pytest.raises(ValidationError):
        AgentMessage(
            sender="agent",
            content="test",
            timestamp=datetime.now(UTC),
        )


def test_agent_message_validation_sender_type() -> None:
    """AgentMessage sender must be a string."""
    with pytest.raises(ValidationError):
        AgentMessage(
            sender=123,  # Invalid: not a string
            content="test",
            timestamp=datetime.now(UTC),
            message_type="info",
        )


def test_agent_message_validation_sender_value() -> None:
    """AgentMessage sender must be one of the known sender types."""
    with pytest.raises(ValidationError) as exc_info:
        AgentMessage(
            sender="unknown_sender",  # Invalid: not in allowed list
            content="test",
            timestamp=datetime.now(UTC),
            message_type="info",
        )
    assert "Input should be 'agent', 'user' or 'system'" in str(exc_info.value)


def test_agent_message_validation_message_type_type() -> None:
    """AgentMessage message_type must be a string."""
    with pytest.raises(ValidationError):
        AgentMessage(
            sender="agent",
            content="test",
            timestamp=datetime.now(UTC),
            message_type=42,  # Invalid: not a string
        )


def test_agent_message_validation_message_type_value() -> None:
    """AgentMessage message_type must be one of the allowed types."""
    with pytest.raises(ValidationError) as exc_info:
        AgentMessage(
            sender="agent",
            content="test",
            timestamp=datetime.now(UTC),
            message_type="invalid_type",  # Invalid: not in allowed list
        )
    assert "Input should be 'text', 'code', 'error', 'success', 'warning' or 'info'" in str(
        exc_info.value
    )


def test_agent_message_validation_naive_timestamp() -> None:
    """AgentMessage timestamp must be timezone-aware."""
    with pytest.raises(ValidationError) as exc_info:
        AgentMessage(
            sender="agent",
            content="test",
            timestamp=datetime(2026, 4, 8, 10, 30, 45),  # Naive datetime
            message_type="info",
        )
    assert "timezone-aware" in str(exc_info.value)


# --- Cross-Model Tests ---


def test_stage_result_with_agent_message_in_data() -> None:
    """Verify StageResult can hold AgentMessage in data field."""
    msg = AgentMessage(
        sender="agent",
        agent_name="Bob",
        content="Processing complete",
        timestamp=datetime.now(UTC),
        message_type="success",
    )
    result = StageResult(
        success=True,
        data={"message": msg.model_dump(by_alias=True)},  # Can serialize message to dict
        confidence=0.9,
    )
    assert result.success is True
    assert result.data["message"]["sender"] == "agent"
    assert result.data["message"]["agentName"] == "Bob"


def test_stage_result_with_list_data() -> None:
    """StageResult can hold list data."""
    data = [
        {"test_case": 1, "expected": "pass"},
        {"test_case": 2, "expected": "pass"},
    ]
    result = StageResult(
        success=True,
        data=data,
        errors=[],
        warnings=[],
        confidence=0.88,
    )
    assert isinstance(result.data, list)
    assert len(result.data) == 2
    assert result.data[0]["test_case"] == 1


def test_agent_message_with_markdown_content() -> None:
    """AgentMessage can hold markdown content."""
    markdown_content = """# Test Report

## Summary
- Total tests: 5
- Passed: 4
- Failed: 1
"""
    msg = AgentMessage(
        sender="agent",
        agent_name="Jack",
        content=markdown_content,
        timestamp=datetime.now(UTC),
        message_type="text",
    )
    assert "# Test Report" in msg.content
    assert "Passed: 4" in msg.content


def test_agent_message_with_json_content() -> None:
    """AgentMessage can hold JSON content."""
    json_content = '{"status": "passed", "count": 5, "duration": 23.45}'
    msg = AgentMessage(
        sender="agent",
        agent_name="Sarah",
        content=json_content,
        timestamp=datetime.now(UTC),
        message_type="code",
    )
    assert '"status": "passed"' in msg.content
    assert json.loads(msg.content)["count"] == 5


def test_stage_result_round_trip_with_complex_data() -> None:
    """StageResult serializes and deserializes complex nested data."""
    complex_data = {
        "requirements": [
            {"id": 1, "text": "Requirement 1"},
            {"id": 2, "text": "Requirement 2"},
        ],
        "metrics": {
            "total": 2,
            "confidence": 0.95,
        },
    }
    original = StageResult(
        success=True,
        data=complex_data,
        errors=[],
        warnings=["Some warning"],
        confidence=0.92,
    )
    json_str = original.model_dump_json()
    reconstructed = StageResult.model_validate_json(json_str)

    assert reconstructed.data["requirements"][0]["id"] == 1
    assert reconstructed.data["metrics"]["confidence"] == 0.95
    assert reconstructed.confidence == 0.92


def test_multiple_agent_messages_in_list() -> None:
    """Multiple AgentMessages can be serialized together."""
    messages = [
        AgentMessage(
            sender="agent",
            agent_name="Alice",
            content="Starting pipeline",
            timestamp=datetime(2026, 4, 8, 10, 0, 0, tzinfo=UTC),
            message_type="info",
        ),
        AgentMessage(
            sender="agent",
            agent_name="Bob",
            content="Requirements extracted",
            timestamp=datetime(2026, 4, 8, 10, 5, 0, tzinfo=UTC),
            message_type="success",
        ),
    ]

    # Serialize to JSON array
    json_array = "[" + ",".join(msg.model_dump_json() for msg in messages) + "]"
    data = json.loads(json_array)

    assert len(data) == 2
    assert data[0]["sender"] == "agent"
    assert data[0]["agent_name"] == "Alice"
    assert data[1]["message_type"] == "success"
