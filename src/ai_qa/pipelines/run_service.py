"""Pipeline run lifecycle helpers for project-scoped execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ai_qa.db.models import PipelineRun


class PipelineRunService:
    """Create and update project-scoped pipeline run records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def start_run(
        self,
        *,
        project_id: UUID,
        started_by_user_id: UUID,
        provider: str | None = None,
        model: str | None = None,
        config_summary: dict[str, Any] | None = None,
    ) -> PipelineRun:
        """Create a running pipeline run for a project action."""
        pipeline_run = PipelineRun(
            project_id=project_id,
            started_by_user_id=started_by_user_id,
            status="running",
            started_at=datetime.now(UTC),
            provider=provider,
            model=model,
            config_summary=config_summary,
        )
        self.db.add(pipeline_run)
        self.db.commit()
        self.db.refresh(pipeline_run)
        return pipeline_run

    def mark_completed(self, pipeline_run_id: UUID, summary: dict[str, Any] | None = None) -> None:
        """Mark a pipeline run as completed if it still exists."""
        self._finish(pipeline_run_id, "completed", summary)

    def mark_failed(self, pipeline_run_id: UUID, summary: dict[str, Any] | None = None) -> None:
        """Mark a pipeline run as failed if it still exists."""
        self._finish(pipeline_run_id, "failed", summary)

    def _finish(
        self,
        pipeline_run_id: UUID,
        status: str,
        summary: dict[str, Any] | None,
    ) -> None:
        pipeline_run = self.db.get(PipelineRun, pipeline_run_id)
        if pipeline_run is None:
            return
        pipeline_run.status = status
        pipeline_run.completed_at = datetime.now(UTC)
        if summary:
            existing_summary = pipeline_run.config_summary or {}
            pipeline_run.config_summary = {**existing_summary, **summary}
        self.db.commit()
