"""Intent-level artifact adapter for project-scoped pipeline agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from ai_qa.artifacts.service import ArtifactService
from ai_qa.db.models import Artifact
from ai_qa.pipelines.context import PipelineContext


@dataclass(frozen=True)
class PipelineArtifact:
    """Small DTO for artifact content consumed by pipeline agents."""

    id: UUID
    name: str
    kind: str
    content: str
    version: int


class PipelineArtifactAdapter:
    """Translate pipeline intent into ArtifactService operations."""

    def __init__(self, context: PipelineContext) -> None:
        if context.artifact_service is None:
            raise ValueError("PipelineArtifactAdapter requires an ArtifactService")
        self.context = context
        self.service: ArtifactService = context.artifact_service

    def save_requirement_page(self, name: str, markdown: str) -> Artifact:
        """Persist an approved requirement page as project-scoped markdown content."""
        return self._save_text(kind="requirements", name=name, content=markdown)

    def load_requirement_markdown(self) -> list[PipelineArtifact]:
        """Load all requirement markdown artifacts for the current project."""
        return self._load_text_artifacts(kind="requirements")

    def save_test_case(self, name: str, test_case: str | dict[str, Any]) -> Artifact:
        """Persist an approved test case as stable JSON/text content."""
        content = self._json_content(test_case)
        return self._save_text(kind="testcase", name=name, content=content)

    def load_test_cases(self) -> list[PipelineArtifact]:
        """Load all approved test case artifacts for the current project."""
        return self._load_text_artifacts(kind="testcase")

    def save_script(self, name: str, script_content: str) -> Artifact:
        """Persist an approved automation script as a project-scoped artifact."""
        return self._save_text(kind="playwright_script", name=name, content=script_content)

    def load_scripts(self) -> list[PipelineArtifact]:
        """Load all project-scoped Playwright script artifacts."""
        return self._load_text_artifacts(kind="playwright_script")

    def save_metadata(self, name: str, metadata: dict[str, Any]) -> Artifact:
        """Persist metadata as a JSON configuration artifact."""
        return self._save_text(
            kind="configuration",
            name=name,
            content=json.dumps(metadata, indent=2, sort_keys=True, default=str),
        )

    def _save_text(self, *, kind: str, name: str, content: str) -> Artifact:
        return self.service.save_artifact(
            project_id=self.context.project_id,
            owner_user_id=self.context.user_id,
            pipeline_run_id=self.context.pipeline_run_id,
            kind=kind,
            name=name,
            content=content,
        )

    def _load_text_artifacts(self, *, kind: str) -> list[PipelineArtifact]:
        artifacts = self.service.list_artifacts(project_id=self.context.project_id, kind=kind)
        return [self._to_pipeline_artifact(artifact) for artifact in artifacts]

    def _to_pipeline_artifact(self, artifact: Artifact) -> PipelineArtifact:
        content_bytes = self.service.read_current_content(artifact)
        return PipelineArtifact(
            id=artifact.id,
            name=artifact.name,
            kind=artifact.kind,
            content=content_bytes.decode("utf-8"),
            version=artifact.current_version,
        )

    def _json_content(self, value: str | dict[str, Any]) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2, sort_keys=True, default=str)
