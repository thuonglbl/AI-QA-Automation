"""Project-scoped artifact API routes."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.api.projects import RESOURCE_NOT_FOUND_DETAIL, ProjectAccessDependency
from ai_qa.artifacts.service import ARTIFACT_KINDS, ArtifactService
from ai_qa.artifacts.storage import ArtifactStorage, S3ArtifactStorage
from ai_qa.config import AppSettings
from ai_qa.db.models import Artifact, Project, User

MAX_ARTIFACT_CONTENT_CHARS = 1_000_000
CONTENT_UNAVAILABLE_DETAIL = "Artifact content unavailable"

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)


def get_artifact_storage() -> ArtifactStorage:
    """Return default artifact storage; tests may override this dependency."""
    settings = AppSettings()
    return S3ArtifactStorage(
        endpoint_url=settings.seaweedfs_endpoint,
        access_key=settings.seaweedfs_access_key,
        secret_key=settings.seaweedfs_secret_key,
        bucket_name=settings.seaweedfs_bucket,
        secure=settings.seaweedfs_secure,
    )


ArtifactStorageDependency = Depends(get_artifact_storage)

router = APIRouter(prefix="/projects/{project_id}/artifacts", tags=["artifacts"])


class ArtifactVersionSummary(BaseModel):
    """Secret-free artifact version metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    artifact_id: UUID
    version: int
    content_hash: str
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class ArtifactResponse(BaseModel):
    """Safe artifact metadata response without ORM relationship graphs."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    agent_run_id: UUID | None
    kind: str
    name: str
    current_version: int
    created_at: datetime
    updated_at: datetime
    created_by_user_id: UUID | None = None
    updated_by_user_id: UUID | None = None
    thread_id: UUID | None = None
    source_type: str | None = None
    source_url: str | None = None
    warnings: list[dict[str, Any]] | None = None
    title: str | None = None
    parent_source_id: str | None = None


class ArtifactTreeEntry(ArtifactResponse):
    """Artifact tree entry with resolved creator/updater display names.

    Extends ``ArtifactResponse`` with optional resolved display-name fields.
    Keeps all base fields so entries remain assignable to the frontend ``Artifact``
    type (id, name, etc.) — required to keep 10-7/10-8 onSelectArtifact wiring.
    Do NOT add display fields to ``ArtifactResponse`` itself (frozen contract).
    """

    created_by_display: str | None = None
    updated_by_display: str | None = None


class ArtifactTreeFolder(BaseModel):
    """A single browse folder in the artifact tree."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    prefix: str | None
    required: bool
    is_empty: bool
    entries: list[ArtifactTreeEntry]


class ArtifactTreeResponse(BaseModel):
    """Folder-structured artifact tree for a project."""

    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    folders: list[ArtifactTreeFolder]


class ArtifactDetailResponse(ArtifactResponse):
    """Artifact metadata with immutable version summaries."""

    versions: list[ArtifactVersionSummary]


class ArtifactContentResponse(BaseModel):
    """JSON-safe current content payload."""

    artifact_id: UUID
    version: int
    content: str
    content_encoding: Literal["text", "base64"]


class ArtifactCreateRequest(BaseModel):
    """Request body for creating a project-scoped artifact."""

    kind: str
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(max_length=MAX_ARTIFACT_CONTENT_CHARS)
    content_encoding: Literal["text", "base64"] = "text"
    agent_run_id: UUID | None = None

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        if value not in ARTIFACT_KINDS:
            raise ValueError("Unsupported artifact kind")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        clean_value = value.strip()
        if not clean_value:
            raise ValueError("Artifact name must not be blank")
        return clean_value


class ArtifactVersionCreateRequest(BaseModel):
    """Request body for appending edited artifact content."""

    content: str = Field(max_length=MAX_ARTIFACT_CONTENT_CHARS)
    content_encoding: Literal["text", "base64"] = "text"


def _decode_content(content: str, encoding: Literal["text", "base64"]) -> str | bytes:
    if encoding == "text":
        return content
    try:
        decoded = base64.b64decode(content, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=422, detail="Invalid base64 artifact content") from exc
    if len(decoded) > MAX_ARTIFACT_CONTENT_CHARS:
        raise HTTPException(status_code=413, detail="Artifact content too large")
    return decoded


def _artifact_response(artifact: Artifact) -> ArtifactResponse:
    return ArtifactResponse.model_validate(artifact)


def _artifact_detail_response(artifact: Artifact) -> ArtifactDetailResponse:
    versions = sorted(artifact.versions, key=lambda version: version.version)
    return ArtifactDetailResponse(
        id=artifact.id,
        project_id=artifact.project_id,
        agent_run_id=artifact.agent_run_id,
        kind=artifact.kind,
        name=artifact.name,
        current_version=artifact.current_version,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        created_by_user_id=artifact.created_by_user_id,
        updated_by_user_id=artifact.updated_by_user_id,
        thread_id=artifact.thread_id,
        source_type=artifact.source_type,
        source_url=artifact.source_url,
        warnings=artifact.warnings,
        versions=[ArtifactVersionSummary.model_validate(version) for version in versions],
    )


def _content_response(artifact: Artifact, content: bytes) -> ArtifactContentResponse:
    try:
        return ArtifactContentResponse(
            artifact_id=artifact.id,
            version=artifact.current_version,
            content=content.decode("utf-8"),
            content_encoding="text",
        )
    except UnicodeDecodeError:
        return ArtifactContentResponse(
            artifact_id=artifact.id,
            version=artifact.current_version,
            content=base64.b64encode(content).decode("ascii"),
            content_encoding="base64",
        )


@router.get("/tree", response_model=ArtifactTreeResponse)
async def get_artifact_tree(
    project_id: UUID,
    project: Project = ProjectAccessDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> ArtifactTreeResponse:
    """Return the folder-structured artifact tree with resolved creator/updater names.

    Always includes the 4 browse folders (requirements, test_cases, test_scripts,
    reports) even when empty. Entries are grouped by logical folder — fixing the
    silent drop of sibling kinds (raw_html, playwright_script) from the flat list.
    Creator/updater display names are resolved server-side (only display_name, no email).
    Non-members receive 404 (no project path leak).
    """
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    try:
        raw_folders = ArtifactService(db, storage).list_artifact_tree(project_id=project.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    folders = [
        ArtifactTreeFolder(
            name=f["name"],
            prefix=f["prefix"],
            required=f["required"],
            is_empty=f["is_empty"],
            entries=[
                ArtifactTreeEntry(
                    id=e["id"],
                    project_id=e["project_id"],
                    agent_run_id=e["agent_run_id"],
                    kind=e["kind"],
                    name=e["name"],
                    current_version=e["current_version"],
                    created_at=e["created_at"],
                    updated_at=e["updated_at"],
                    created_by_user_id=e["created_by_user_id"],
                    updated_by_user_id=e["updated_by_user_id"],
                    thread_id=e["thread_id"],
                    created_by_display=e["created_by_display"],
                    updated_by_display=e["updated_by_display"],
                    source_type=e["source_type"],
                    source_url=e["source_url"],
                    warnings=e["warnings"],
                    title=e["title"],
                    parent_source_id=e["parent_source_id"],
                )
                for e in f["entries"]
            ],
        )
        for f in raw_folders
    ]
    return ArtifactTreeResponse(project_id=project.id, folders=folders)


@router.get("", response_model=list[ArtifactResponse])
async def list_artifacts(
    project_id: UUID,
    kind: str | None = Query(default=None),
    project: Project = ProjectAccessDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> list[ArtifactResponse]:
    """List project artifacts for members and admins, optionally by kind."""
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    try:
        artifacts = ArtifactService(db, storage).list_artifacts(project_id=project.id, kind=kind)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [_artifact_response(artifact) for artifact in artifacts]


@router.post("", response_model=ArtifactResponse)
async def create_artifact(
    project_id: UUID,
    request: ArtifactCreateRequest,
    project: Project = ProjectAccessDependency,
    current_user: User = CurrentUserDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> ArtifactResponse:
    """Create artifact metadata and version 1 content for an authorized project user."""
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    try:
        artifact = ArtifactService(db, storage).save_artifact(
            project_id=project.id,
            owner_user_id=current_user.id,
            kind=request.kind,
            name=request.name,
            content=_decode_content(request.content, request.content_encoding),
            agent_run_id=request.agent_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Broadcast artifact change event (best-effort, non-blocking)
    try:
        from ai_qa.api.websocket import broadcast_artifact_change

        await broadcast_artifact_change(
            project_id=str(project.id),
            artifact_id=str(artifact.id),
            change_type="created",
        )
    except Exception:
        pass

    return _artifact_response(artifact)


@router.get("/{artifact_id}", response_model=ArtifactDetailResponse)
async def get_artifact(
    project_id: UUID,
    artifact_id: UUID,
    project: Project = ProjectAccessDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> ArtifactDetailResponse:
    """Return artifact metadata and version history after project access succeeds."""
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    artifact = ArtifactService(db, storage).get_artifact(
        project_id=project.id, artifact_id=artifact_id
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    return _artifact_detail_response(artifact)


@router.get("/{artifact_id}/content", response_model=ArtifactContentResponse)
async def read_artifact_content(
    project_id: UUID,
    artifact_id: UUID,
    project: Project = ProjectAccessDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> ArtifactContentResponse:
    """Return current artifact content as UTF-8 text or base64 for binary bytes."""
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    service = ArtifactService(db, storage)
    artifact = service.get_artifact(project_id=project.id, artifact_id=artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    try:
        content = service.read_current_content(artifact)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=CONTENT_UNAVAILABLE_DETAIL) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _content_response(artifact, content)


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    project_id: UUID,
    artifact_id: UUID,
    project: Project = ProjectAccessDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete an artifact and its storage objects after project access check."""
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    deleted = ArtifactService(db, storage).delete_artifact(
        project_id=project.id, artifact_id=artifact_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)

    # Broadcast artifact change event (best-effort, non-blocking)
    try:
        from ai_qa.api.websocket import broadcast_artifact_change

        await broadcast_artifact_change(
            project_id=str(project.id),
            artifact_id=str(artifact_id),
            change_type="deleted",
        )
    except Exception:
        pass


@router.post("/{artifact_id}/versions", response_model=ArtifactResponse)
async def create_artifact_version(
    project_id: UUID,
    artifact_id: UUID,
    request: ArtifactVersionCreateRequest,
    project: Project = ProjectAccessDependency,
    current_user: User = CurrentUserDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
    db: Session = DbSessionDependency,
) -> ArtifactResponse:
    """Append an edited content version without changing artifact name or kind."""
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)
    service = ArtifactService(db, storage)
    try:
        updated = service.create_version(
            project_id=project.id,
            artifact_id=artifact_id,
            created_by_user_id=current_user.id,
            content=_decode_content(request.content, request.content_encoding),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)

    # Broadcast artifact change event (best-effort, non-blocking)
    try:
        from ai_qa.api.websocket import broadcast_artifact_change

        await broadcast_artifact_change(
            project_id=str(project.id),
            artifact_id=str(artifact_id),
            change_type="updated",
        )
    except Exception:
        pass

    return _artifact_response(updated)


__all__ = [
    "ArtifactContentResponse",
    "ArtifactCreateRequest",
    "ArtifactDetailResponse",
    "ArtifactResponse",
    "ArtifactTreeEntry",
    "ArtifactTreeFolder",
    "ArtifactTreeResponse",
    "ArtifactVersionCreateRequest",
    "ArtifactVersionSummary",
    "router",
]
