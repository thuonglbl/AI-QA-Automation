"""Shared Pydantic models for the AI QA automation pipeline.

All pipeline stages exchange data through typed models, never raw dicts.
This ensures type safety, validation, and proper JSON serialization.

Models:
  - StageResult: Wrapper for pipeline stage output (success, data, errors, warnings, confidence)
  - AgentMessage: Agent-to-frontend communication (sender, content, timestamp, message_type)
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class StageResult(BaseModel):
    """Validated output from any pipeline stage.

    This model wraps the result of processing through a stage (e.g., Requirements extraction,
    Test Case generation, Script generation). Stages MUST return StageResult, not raw dicts.

    Attributes:
        success: True if stage completed without fatal errors.
        data: The stage's output payload (test requirements, test cases, scripts, execution results, etc.).
              Specific type depends on stage. Can be None if stage failed or produced no data.
        errors: List of fatal errors that prevented successful processing (empty if success=True).
        warnings: List of non-fatal warnings (low confidence, missing fields, retries needed, etc.).
        confidence: Overall confidence in the result (0.0 to 1.0), or None if not applicable.
                   Used by downstream stages to decide whether to proceed or flag for review.
    """

    success: bool = Field(description="Stage succeeded without fatal errors")
    data: Any | None = Field(
        default=None, description="Stage output payload (type depends on stage)"
    )
    errors: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Fatal errors that blocked processing (max 100 items)",
    )
    warnings: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="Non-fatal warnings (max 100 items)",
    )
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence in result (0.0-1.0), None if not applicable",
    )

    model_config = ConfigDict(validate_assignment=True)

    @model_validator(mode="after")
    def validate_success_errors_consistency(self) -> "StageResult":
        """Ensure consistency: if success=True, errors must be empty."""
        if self.success is True and self.errors:
            raise ValueError("success=True but errors list is not empty — inconsistent state")
        return self


class AgentMessage(BaseModel):
    """Typed message from an agent to the frontend UI.

    Each agent (Alice, Bob, Mary, Sarah, Jack) sends progress updates, results, and user feedback
    through AgentMessage. The frontend subscribes to these messages via WebSocket and updates the UI.

    Attributes:
        id: Unique message identifier (auto-generated UUID).
        sender: Who sent the message (agent, user, or system).
        agent_name: Agent name in Title Case (required when sender is 'agent').
        content: Message text or structured data (markdown, error trace, approval prompt, etc.).
        timestamp: When the message was generated (timezone-aware datetime, ISO 8601 format in JSON).
        message_type: Classification of message type for UI rendering.
        metadata: Optional additional data.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique message identifier",
    )
    sender: Literal["agent", "user", "system"] = Field(
        description="Who sent the message (agent, user, or system)"
    )
    agent_name: Literal["Alice", "Bob", "Mary", "Sarah", "Jack"] | None = Field(
        default=None,
        alias="agentName",
        description="Agent name in Title Case (required when sender is 'agent')",
    )
    content: str = Field(description="Message text or structured data (markdown, JSON, etc.)")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When the message was generated (timezone-aware datetime)",
    )
    message_type: Literal["text", "code", "error", "success", "warning", "info"] = Field(
        alias="messageType",
        description="Message classification for UI rendering",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional additional data",
    )

    model_config = ConfigDict(validate_assignment=True, populate_by_name=True)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware for unambiguous ISO 8601 serialization."""
        if v.tzinfo is None:
            raise ValueError(
                "timestamp must be timezone-aware (e.g., use datetime.now(timezone.utc))"
            )
        return v

    @field_serializer("timestamp", when_used="json")
    def serialize_timestamp(self, value: datetime) -> str:
        """Serialize datetime to ISO 8601 format in JSON."""
        return value.isoformat()


# =============================================================================
# Configuration Models (Epic 2-8)
# =============================================================================


class ProviderConfig(BaseModel):
    """AI provider configuration.

    Stored in workspace/configuration/provider.json.

    Attributes:
        provider: Provider identifier (claude, on-premises, etc.)
        provider_name: Human-readable provider name
        endpoint: API endpoint URL
        credential_reference: Reference to credential storage (env://KEY_NAME)
        tested_at: ISO 8601 timestamp of last connection test
        test_result: Result of connection test (success/failed)
    """

    provider: str = Field(description="Provider identifier")
    provider_name: str = Field(description="Human-readable provider name")
    endpoint: str = Field(description="API endpoint URL")
    credential_reference: str = Field(description="Credential storage reference")
    tested_at: str = Field(description="ISO 8601 timestamp of connection test")
    test_result: Literal["success", "failed"] = Field(description="Connection test result")

    model_config = ConfigDict(validate_assignment=True)


class AgentModelConfig(BaseModel):
    """Per-agent model configuration.

    Defines which model and settings an agent uses.

    Attributes:
        model: Model identifier (e.g., claude-3-opus-20240229)
        temperature: Sampling temperature (0.0-2.0)
        prompt_template: Name of prompt template to use
        tools: List of tool names available to the agent
    """

    model: str = Field(description="Model identifier")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature")
    prompt_template: str = Field(description="Prompt template name")
    tools: list[str] = Field(default_factory=list, description="Available tool names")

    model_config = ConfigDict(validate_assignment=True)


class AgentsConfig(BaseModel):
    """Complete agents configuration.

    Stored in workspace/configuration/agents.json.

    Attributes:
        version: Configuration schema version
        updated_at: ISO 8601 timestamp of last update
        agents: Map of agent name to AgentModelConfig
    """

    version: str = Field(default="1.0", description="Configuration schema version")
    updated_at: str = Field(description="ISO 8601 timestamp of last update")
    agents: dict[str, AgentModelConfig] = Field(description="Per-agent configurations")

    model_config = ConfigDict(validate_assignment=True)


class AliceConfiguration(BaseModel):
    """Complete Alice step output configuration.

    Combines provider and agents configuration for persistence.

    Attributes:
        provider: Provider configuration
        agents: Agents configuration with model assignments
    """

    provider: ProviderConfig = Field(description="Provider configuration")
    agents: AgentsConfig = Field(description="Agents configuration")

    model_config = ConfigDict(validate_assignment=True)


# =============================================================================
# Test Case Models (Epic 4)
# =============================================================================


class TestCaseStep(BaseModel):
    """A single step in a test case.

    Designed for browser-use automation with clear action-target pairs.

    Attributes:
        number: Step sequence number (1-indexed)
        action: The action to perform (e.g., "Enter username in #username field")
        target: What element/page the action targets (e.g., "username input")
        data: Optional input data for the action (e.g., "testuser123")
    """

    number: int = Field(ge=1, description="Step sequence number")
    action: str = Field(description="The action to perform")
    target: str = Field(description="Target element or page")
    data: str | None = Field(default=None, description="Optional input data for the action")

    model_config = ConfigDict(validate_assignment=True)


class TestCase(BaseModel):
    """Structured test case for browser automation.

    Generated by Mary agent from requirements, optimized for browser-use execution.

    Attributes:
        title: Test case title (kebab-case filename derived from this)
        preconditions: List of conditions that must be met before test execution
        steps: Ordered list of test steps with action-target pairs
        expected_results: List of expected outcomes after test execution
        automation_hints: Optional hints for automation (selectors, test IDs)
        tags: Optional categorization tags (e.g., ["smoke", "regression"])
    """

    title: str = Field(description="Test case title")
    preconditions: list[str] = Field(default_factory=list, description="Pre-execution conditions")
    steps: list[TestCaseStep] = Field(default_factory=list, description="Ordered test steps")
    expected_results: list[str] = Field(default_factory=list, description="Expected outcomes")
    automation_hints: list[str] = Field(
        default_factory=list, description="Automation selectors/hints"
    )
    tags: list[str] = Field(default_factory=list, description="Categorization tags")

    model_config = ConfigDict(validate_assignment=True)

    @property
    def filename(self) -> str:
        """Generate kebab-case filename from title."""
        import re

        # Convert to lowercase, replace non-alphanumeric with hyphens
        kebab = re.sub(r"[^a-z0-9]+", "-", self.title.lower())
        return kebab.strip("-")
