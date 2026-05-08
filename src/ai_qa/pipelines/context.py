"""Project-scoped pipeline context utilities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from ai_qa.artifacts.service import ArtifactService


@dataclass(slots=True)
class PipelineContext:
    """Authorized project/user context carried through pipeline dispatch."""

    project_id: UUID
    user_id: UUID
    user_email: str
    artifact_service: ArtifactService | None = None
    pipeline_run_id: UUID | None = None
