"""Service layer for project-scoped artifacts and versions."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, TypedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ai_qa.artifacts.storage import ArtifactStorage, LocalArtifactStorage, folder_for_kind
from ai_qa.db.models import Artifact, ArtifactVersion, User
from ai_qa.threads.models import AgentRun, Thread

ARTIFACT_KINDS = frozenset(
    {
        "configuration",
        "execution_screenshot",  # Story 14.3 — execution-run screenshot (browses under reports)
        "image",
        "log",  # Story 14.3 — execution run log
        "markdown",
        "mermaid",
        "playwright_script",
        "raw_html",
        "report",
        "requirements",
        "screenshot",
        "testcase",
        "testscript",
        "trace",  # Story 14.3 — execution Playwright trace
        "video",  # execution Playwright video (browses under reports)
    }
)

REQUIRED_ARTIFACT_FOLDERS = ("requirements", "test_cases", "test_scripts")


class ArtifactTreeEntryDict(TypedDict):
    """Typed dict shape for a single artifact entry in the tree response."""

    id: UUID
    project_id: UUID
    agent_run_id: UUID | None
    kind: str
    name: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    thread_id: UUID | None
    created_by_display: str | None
    updated_by_display: str | None
    source_type: str | None
    source_url: str | None
    warnings: list[dict[str, Any]] | None
    title: str | None
    parent_source_id: str | None
    ancestor_source_ids: list[str] | None


class ArtifactTreeFolderDict(TypedDict):
    """Typed dict shape for a single browse folder in the tree response."""

    name: str
    prefix: str | None
    required: bool
    is_empty: bool
    entries: list[ArtifactTreeEntryDict]


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
        agent_run_id: UUID | None = None,
        thread_id: UUID | None = None,
        source_type: str | None = None,
        source_url: str | None = None,
        warnings: list[dict[str, Any]] | None = None,
        title: str | None = None,
        parent_source_id: str | None = None,
        ancestor_source_ids: list[str] | None = None,
    ) -> Artifact:
        """Create an artifact and initial version row for project-owned content."""
        self._validate_kind(kind)
        clean_name = self._validate_name(name)
        self._validate_agent_run(project_id, agent_run_id)
        self._validate_thread(project_id, thread_id)
        content_bytes = _content_to_bytes(content)
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        artifact = Artifact(
            project_id=project_id,
            agent_run_id=agent_run_id,
            thread_id=thread_id,
            created_by_user_id=owner_user_id,
            updated_by_user_id=owner_user_id,
            kind=kind,
            name=clean_name,
            storage_path="pending",
            current_version=1,
            source_type=source_type,
            source_url=source_url,
            warnings=warnings,
            title=title,
            parent_source_id=parent_source_id,
            ancestor_source_ids=ancestor_source_ids,
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
            artifact.updated_by_user_id = created_by_user_id
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

    def delete_artifact(self, *, project_id: UUID, artifact_id: UUID) -> bool:
        """Delete an artifact and all its versioned storage objects.

        Returns True if the artifact was found and deleted, False otherwise.
        Storage cleanup is best-effort — DB delete proceeds even if storage fails.
        """
        artifact = self.db.execute(
            select(Artifact)
            .options(selectinload(Artifact.versions))
            .where(Artifact.project_id == project_id, Artifact.id == artifact_id)
        ).scalar_one_or_none()
        if artifact is None:
            return False

        # Best-effort storage cleanup for all versions
        for version in artifact.versions:
            if version.storage_path:
                self.storage.delete(version.storage_path)
        if artifact.storage_path:
            self.storage.delete(artifact.storage_path)

        self.db.delete(artifact)
        self.db.commit()
        return True

    def read_current_content(self, artifact: Artifact) -> bytes:
        """Read current artifact content from the configured storage backend."""
        return self.storage.read(artifact.storage_path)

    def required_folders(self, project_id: UUID) -> list[str]:
        """Return the three required logical folder prefixes for a project.

        Projection only — does not create objects in storage.
        Story 10.2 uses these to render empty-folder placeholders.
        """
        return [f"projects/{project_id}/{folder}/" for folder in REQUIRED_ARTIFACT_FOLDERS]

    def list_artifact_tree(
        self,
        *,
        project_id: UUID,
    ) -> list[ArtifactTreeFolderDict]:
        """Return the 4 browse folders with entries grouped by logical folder.

        Always includes all 4 browse folders (requirements, test_cases, test_scripts,
        reports) even when empty — the 3 required ones per AC1 and reports to match
        shipped behavior.  Entries are ordered newest-first by ``updated_at``.
        Creator/updater display names are resolved in ONE batch query (no N+1).
        Never creates objects in storage — projection only.
        """
        # Fetch all project artifacts ordered newest-first. Review P4 fix: add Artifact.id
        # as a deterministic tiebreaker so artifacts sharing an updated_at (batch agent
        # output) keep a stable order across refreshes — otherwise paginated rows shuffle
        # between pages on each /tree fetch.
        all_artifacts = list(
            self.db.execute(
                select(Artifact)
                .where(Artifact.project_id == project_id)
                .order_by(Artifact.updated_at.desc(), Artifact.id.desc())
            )
            .scalars()
            .all()
        )

        # Batch-resolve user display names (one query, no N+1, no empty IN())
        user_ids: set[UUID] = set()
        for artifact in all_artifacts:
            if artifact.created_by_user_id is not None:
                user_ids.add(artifact.created_by_user_id)
            if artifact.updated_by_user_id is not None:
                user_ids.add(artifact.updated_by_user_id)

        name_map: dict[UUID, str] = {}
        if user_ids:
            rows = self.db.execute(
                select(User.id, User.display_name).where(User.id.in_(user_ids))
            ).all()
            name_map = {row.id: row.display_name for row in rows}

        # Bucket artifacts into their browse folders
        browse_order = ["requirements", "test_cases", "test_scripts", "reports"]
        required_browse = frozenset(REQUIRED_ARTIFACT_FOLDERS)
        buckets: dict[str, list[ArtifactTreeEntryDict]] = {f: [] for f in browse_order}

        for artifact in all_artifacts:
            browse_folder = folder_for_kind(artifact.kind, artifact.name)
            entry: ArtifactTreeEntryDict = {
                "id": artifact.id,
                "project_id": artifact.project_id,
                "agent_run_id": artifact.agent_run_id,
                "kind": artifact.kind,
                "name": artifact.name,
                "current_version": artifact.current_version,
                "created_at": artifact.created_at,
                "updated_at": artifact.updated_at,
                "created_by_user_id": artifact.created_by_user_id,
                "updated_by_user_id": artifact.updated_by_user_id,
                "thread_id": artifact.thread_id,
                "created_by_display": (
                    name_map.get(artifact.created_by_user_id)
                    if artifact.created_by_user_id is not None
                    else None
                ),
                "updated_by_display": (
                    name_map.get(artifact.updated_by_user_id)
                    if artifact.updated_by_user_id is not None
                    else None
                ),
                "source_type": artifact.source_type,
                "source_url": artifact.source_url,
                "warnings": artifact.warnings,
                "title": artifact.title,
                "parent_source_id": artifact.parent_source_id,
                "ancestor_source_ids": artifact.ancestor_source_ids,
            }
            buckets[browse_folder].append(entry)

        # Build the ordered folder list (requirements, test_cases, test_scripts, reports)
        folders: list[ArtifactTreeFolderDict] = []
        for folder_name in browse_order:
            entries = buckets[folder_name]
            is_required = folder_name in required_browse
            prefix: str | None = f"projects/{project_id}/{folder_name}/" if is_required else None
            folders.append(
                {
                    "name": folder_name,
                    "prefix": prefix,
                    "required": is_required,
                    "is_empty": len(entries) == 0,
                    "entries": entries,
                }
            )

        return folders

    def _validate_kind(self, kind: str) -> None:
        if kind not in ARTIFACT_KINDS:
            raise ValueError("Unsupported artifact kind")

    def _validate_name(self, name: str) -> str:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 255:
            raise ValueError("Artifact name must be between 1 and 255 characters")
        return clean_name

    def _validate_agent_run(self, project_id: UUID, agent_run_id: UUID | None) -> None:
        if agent_run_id is None:
            return
        agent_run = self.db.get(AgentRun, agent_run_id)
        # Assuming AgentRun is tied to a thread which is tied to a project
        if agent_run is None or agent_run.thread.project_id != project_id:
            raise ValueError("Agent run does not belong to project")

    def _validate_thread(self, project_id: UUID, thread_id: UUID | None) -> None:
        if thread_id is None:
            return
        thread = self.db.get(Thread, thread_id)
        if thread is None or thread.project_id != project_id:
            raise ValueError("Thread does not belong to project")


def _content_to_bytes(content: str | bytes) -> bytes:
    return content.encode("utf-8") if isinstance(content, str) else content
