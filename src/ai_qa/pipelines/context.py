"""Project-scoped pipeline context utilities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ai_qa.artifacts.service import ArtifactService


@dataclass(slots=True)
class PipelineContext:
    """Authorized project/user context carried through pipeline dispatch."""

    user_id: UUID
    user_email: str
    project_id: UUID | None = None
    thread_id: UUID | None = None
    artifact_service: ArtifactService | None = None
    agent_run_id: UUID | None = None
    conversation_language: str = "en"
