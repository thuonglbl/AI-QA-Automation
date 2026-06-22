"""Pydantic schemas for Threads."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ThreadBase(BaseModel):
    user_id: UUID
    project_id: UUID | None = None


class ThreadCreate(ThreadBase):
    pass


class ThreadUpdate(BaseModel):
    title: str | None = None
    is_archived: bool | None = None


class ThreadResponse(ThreadBase):
    id: UUID
    current_step: int
    status: str
    title: str | None = None
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MessageBase(BaseModel):
    sender: str
    agent_name: str | None = None
    content: str
    message_type: str = "text"
    message_metadata: dict[str, Any] | None = None


class MessageCreate(MessageBase):
    pass


class MessageResponse(MessageBase):
    id: UUID
    thread_id: UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ThreadDetailsResponse(ThreadResponse):
    messages: list[MessageResponse]
    agent_runs: list[AgentRunResponse]


class AgentRunBase(BaseModel):
    status: str
    summary: str | None = None
    execution_metadata: dict[str, Any] | None = None


class AgentRunCreate(AgentRunBase):
    pass


class AgentRunUpdate(BaseModel):
    status: str | None = None
    summary: str | None = None
    execution_metadata: dict[str, Any] | None = None
    current_step: int | None = None


class AgentRunResponse(AgentRunBase):
    id: UUID
    thread_id: UUID
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AgentConfigEntry(BaseModel):
    """Non-secret per-agent model/settings summary for ProviderConfigResponse."""

    agent: str
    model: str | None = None
    temperature: float = 0.0
    rationale: str = ""


class ProviderConfigResponse(BaseModel):
    """Non-secret provider configuration for a thread (Task 5 / Story 9.7).

    Never contains secrets, API keys, or credential values.
    ``source`` indicates where the config came from:
    - ``"thread"``: from the thread's saved snapshot
    - ``"saved"``: from the per-(user, project) saved default
    - ``"none"``: no config found
    """

    configured: bool
    source: str = Field(default="none")
    provider: str | None = None
    provider_name: str | None = None
    endpoint: str | None = None
    test_result: str | None = None
    tested_at: str | None = None
    agents: list[AgentConfigEntry] = Field(default_factory=list)
