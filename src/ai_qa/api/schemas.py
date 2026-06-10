"""Pydantic schemas for API request/response validation.

These models define the structure of data exchanged between frontend and backend.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    """Request body for /api/start endpoint."""

    step: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Pipeline step to start (1-5)",
    )
    input_data: dict[str, object] = Field(
        default_factory=dict,
        description="Step-specific input data (e.g., Confluence URL for step 2)",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Selected project for authenticated project-scoped pipeline execution",
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Conversation thread ID",
    )


class ActionResponse(BaseModel):
    """Response for pipeline action endpoints."""

    success: bool = Field(description="Whether the action was accepted")
    message: str = Field(description="Human-readable status message")
    current_step: int = Field(description="Current pipeline step after action")
    status: str = Field(description="Agent status (start/processing/review/done)")


class ApproveRequest(BaseModel):
    """Request body for /api/approve endpoint."""

    step: int = Field(ge=1, le=5, description="Step being approved")
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being approved (for paginated review)",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Selected project for authenticated project-scoped pipeline execution",
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Conversation thread ID",
    )


class RejectRequest(BaseModel):
    """Request body for /api/reject endpoint."""

    step: int = Field(ge=1, le=5, description="Step being rejected")
    feedback: str = Field(
        min_length=1,
        max_length=2000,
        description="User feedback explaining why output is rejected",
    )
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being rejected (for paginated review)",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Selected project for authenticated project-scoped pipeline execution",
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Conversation thread ID",
    )


class ContinueRequest(BaseModel):
    """Request body for /api/continue endpoint."""

    from_step: int = Field(ge=1, le=5, description="Step that was just completed")
    project_id: UUID | None = Field(
        default=None,
        description="Selected project for authenticated project-scoped pipeline execution",
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Conversation thread ID",
    )


class SkipRequest(BaseModel):
    """Request body for /api/skip endpoint.

    Used by Sarah agent to skip current script review
    (hand off to automation engineer for manual review).
    """

    step: int = Field(ge=1, le=5, description="Step being processed")
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being skipped (for paginated review)",
    )
    project_id: UUID | None = Field(
        default=None,
        description="Selected project for authenticated project-scoped pipeline execution",
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Conversation thread ID",
    )


class NavigateRequest(BaseModel):
    """Request body for /api/navigate endpoint.

    Used for navigating between items during review (Next/Previous).
    """

    step: int = Field(ge=1, le=5, description="Step being processed")
    direction: str = Field(
        pattern="^(next|previous)$",
        description="Navigation direction: 'next' or 'previous'",
    )
    current_index: int = Field(ge=0, description="Current item index")
    project_id: UUID | None = Field(
        default=None,
        description="Selected project for authenticated project-scoped pipeline execution",
    )
    thread_id: UUID | None = Field(
        default=None,
        description="Conversation thread ID",
    )


class ConversationMessage(BaseModel):
    """Single message in the conversation history."""

    id: str = Field(description="Unique message ID")
    sender: Literal["agent", "user", "system"] = Field(description="Message sender type")
    agent_name: str | None = Field(default=None, description="Agent name if sender is 'agent'")
    content: str = Field(description="Message content (markdown supported)")
    timestamp: datetime = Field(description="ISO 8601 timestamp")
    message_type: str = Field(default="text", description="Message type for styling")
    metadata: dict[str, object] | None = Field(default=None, description="Optional metadata")


class ConversationData(BaseModel):
    """Complete conversation data for persistence."""

    messages: list[ConversationMessage] = Field(default_factory=list, description="Chat messages")
    current_step: int = Field(default=1, ge=1, le=5, description="Current pipeline step")
    status: str = Field(default="start", description="Current pipeline status")
    current_agent: str = Field(default="Alice", description="Current agent name")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Last update timestamp"
    )


class ConversationSaveRequest(BaseModel):
    """Request to save conversation data."""

    conversation: ConversationData = Field(description="Conversation data to save")
