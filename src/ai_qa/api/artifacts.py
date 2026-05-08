"""Project-scoped artifact API routes."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.api.projects import RESOURCE_NOT_FOUND_DETAIL, ProjectAccessDependency
from ai_qa.artifacts.service import ARTIFACT_KINDS, ArtifactService
from ai_qa.artifacts.storage import ArtifactStorage, LocalArtifactStorage
from ai_qa.db.models import Artifact, Project, User

MAX_ARTIFACT_CONTENT_CHARS = 1_000_000
CONTENT_UNAVAILABLE_DETAIL = "Artifact content unavailable"

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)


def get_artifact_storage() -> ArtifactStorage:
    """Return default artifact storage; tests may override this dependency."""
    return LocalArtifactStorage()


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
    pipeline_run_id: UUID | None
    kind: str
    name: str
    current_version: int
    created_at: datetime
    updated_at: datetime


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
    pipeline_run_id: UUID | None = None

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
        pipeline_run_id=artifact.pipeline_run_id,
        kind=artifact.kind,
        name=artifact.name,
        current_version=artifact.current_version,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
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
            pipeline_run_id=request.pipeline_run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    return _artifact_response(updated)


__all__ = [
    "ArtifactContentResponse",
    "ArtifactCreateRequest",
    "ArtifactDetailResponse",
    "ArtifactResponse",
    "ArtifactVersionCreateRequest",
    "ArtifactVersionSummary",
    "router",
]
