"""Service layer for project-scoped artifacts and versions."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ai_qa.artifacts.storage import ArtifactStorage, LocalArtifactStorage
from ai_qa.db.models import Artifact, ArtifactVersion, PipelineRun

ARTIFACT_KINDS = frozenset(
    {
        "configuration",
        "image",
        "markdown",
        "mermaid",
        "playwright_script",
        "raw_html",
        "report",
        "requirements",
        "screenshot",
        "testcase",
        "testscript",
    }
)


class ArtifactService:
    """Coordinate artifact metadata persistence with content storage."""

    def __init__(self, db: Session, storage: ArtifactStorage | None = None) -> None:
        self.db = db
        self.storage = storage or LocalArtifactStorage()

    def save_artifact(
        self,
        *,
        project_id: UUID,
        owner_user_id: UUID | None,
        kind: str,
        name: str,
        content: str | bytes,
        pipeline_run_id: UUID | None = None,
    ) -> Artifact:
        """Create an artifact and initial version row for project-owned content."""
        self._validate_kind(kind)
        clean_name = self._validate_name(name)
        self._validate_pipeline_run(project_id, pipeline_run_id)
        content_bytes = _content_to_bytes(content)
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        artifact = Artifact(
            project_id=project_id,
            pipeline_run_id=pipeline_run_id,
            kind=kind,
            name=clean_name,
            storage_path="pending",
            current_version=1,
        )
        self.db.add(artifact)
        self.db.flush()

        storage_path: str | None = None
        try:
            storage_path = self.storage.write(
                project_id=project_id,
                artifact_id=artifact.id,
                version=1,
                kind=kind,
                name=clean_name,
                content=content,
            )
            artifact.storage_path = storage_path
            artifact.versions.append(
                ArtifactVersion(
                    version=1,
                    content_hash=content_hash,
                    storage_path=storage_path,
                    created_by_user_id=owner_user_id,
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            if storage_path is not None:
                self.storage.delete(storage_path)
            raise

        self.db.refresh(artifact)
        return artifact

    def create_version(
        self,
        *,
        project_id: UUID,
        artifact_id: UUID,
        created_by_user_id: UUID | None,
        content: str | bytes,
    ) -> Artifact | None:
        """Append a version to an artifact after validating its project boundary."""
        artifact = self.db.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id, Artifact.id == artifact_id)
            .with_for_update()
        ).scalar_one_or_none()
        if artifact is None:
            return None

        next_version = artifact.current_version + 1
        content_bytes = _content_to_bytes(content)
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        storage_path: str | None = None
        try:
            storage_path = self.storage.write(
                project_id=artifact.project_id,
                artifact_id=artifact.id,
                version=next_version,
                kind=artifact.kind,
                name=artifact.name,
                content=content,
            )
            artifact.current_version = next_version
            artifact.storage_path = storage_path
            artifact.versions.append(
                ArtifactVersion(
                    version=next_version,
                    content_hash=content_hash,
                    storage_path=storage_path,
                    created_by_user_id=created_by_user_id,
                )
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            if storage_path is not None:
                self.storage.delete(storage_path)
            raise

        self.db.refresh(artifact)
        return artifact

    def list_artifacts(self, *, project_id: UUID, kind: str | None = None) -> list[Artifact]:
        """List project artifacts, optionally filtered by centralized kind values."""
        if kind is not None:
            self._validate_kind(kind)
        query = select(Artifact).where(Artifact.project_id == project_id).order_by(Artifact.name)
        if kind is not None:
            query = query.where(Artifact.kind == kind)
        return list(self.db.execute(query).scalars().all())

    def get_artifact(self, *, project_id: UUID, artifact_id: UUID) -> Artifact | None:
        """Return one artifact with versions only inside the requested project."""
        return self.db.execute(
            select(Artifact)
            .options(selectinload(Artifact.versions))
            .where(Artifact.project_id == project_id, Artifact.id == artifact_id)
        ).scalar_one_or_none()

    def read_current_content(self, artifact: Artifact) -> bytes:
        """Read current artifact content from the configured storage backend."""
        return self.storage.read(artifact.storage_path)

    def _validate_kind(self, kind: str) -> None:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unsupported artifact kind")

    def _validate_name(self, name: str) -> str:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Artifact name must be between 1 and 255 characters")
        return clean_name

    def _validate_pipeline_run(self, project_id: UUID, pipeline_run_id: UUID | None) -> None:
        if pipeline_run_id is None:
            return
        pipeline_run = self.db.get(PipelineRun, pipeline_run_id)
        if pipeline_run is None or pipeline_run.project_id != project_id:
            raise ValueError("Pipeline run does not belong to project")


def _content_to_bytes(content: str | bytes) -> bytes:
    return content.encode("utf-8") if isinstance(content, str) else content
