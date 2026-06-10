# Blind Hunter Prompt — Story 6.5

You are the **Blind Hunter** adversarial reviewer.

## Scope

Review only the diff/change contents below. You receive **no project context, no spec, no prior conversation**.

## Instructions

Find concrete defects, security bugs, data-loss risks, correctness bugs, race conditions, API contract problems, and test blind spots evident from the change itself.

Output findings as a Markdown list. Each finding must include:
- one-line title
- severity: Critical / High / Medium / Low
- evidence from the diff
- why it matters
- suggested fix

If no findings, say `No findings`.

## Change Summary

Tracked changes:
- `_bmad-output/implementation-artifacts/sprint-status.yaml`: status moved to review
- `src/ai_qa/api/app.py`: includes artifact router under `/api`
- `src/ai_qa/db/models.py`: changes `PipelineRun.config_summary` to SQLAlchemy `JSON().with_variant(JSONB, "postgresql")`

New files:
- `src/ai_qa/api/artifacts.py`
- `src/ai_qa/artifacts/__init__.py`
- `src/ai_qa/artifacts/service.py`
- `src/ai_qa/artifacts/storage.py`
- `tests/test_artifact_api.py`
- `tests/test_artifact_service.py`

## Diff / File Contents to Review

### src/ai_qa/api/artifacts.py

```python
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

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)


def get_artifact_storage() -> ArtifactStorage:
    return LocalArtifactStorage()

ArtifactStorageDependency = Depends(get_artifact_storage)
router = APIRouter(prefix="/projects/{project_id}/artifacts", tags=["artifacts"])

class ArtifactVersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    artifact_id: UUID
    version: int
    content_hash: str
    storage_path: str | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime

class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    pipeline_run_id: UUID | None
    kind: str
    name: str
    storage_path: str
    current_version: int
    created_at: datetime
    updated_at: datetime

class ArtifactDetailResponse(ArtifactResponse):
    versions: list[ArtifactVersionSummary]

class ArtifactContentResponse(BaseModel):
    artifact_id: UUID
    version: int
    content: str
    content_encoding: Literal["text", "base64"]

class ArtifactCreateRequest(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=255)
    content: str
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
    content: str
    content_encoding: Literal["text", "base64"] = "text"

def _decode_content(content: str, encoding: Literal["text", "base64"]) -> str | bytes:
    if encoding == "text":
        return content
    try:
        return base64.b64decode(content, validate=True)
    except binascii.Error as exc:
        raise HTTPException(status_code=422, detail="Invalid base64 artifact content") from exc

# Routes: list/create/detail/content/create-version use ProjectAccessDependency,
# CurrentUserDependency for writes, ArtifactService for persistence, and return explicit Pydantic schemas.
```

### src/ai_qa/artifacts/service.py

```python
ARTIFACT_KINDS = frozenset({"configuration", "markdown", "mermaid", "playwright_script", "report", "requirements", "screenshot", "testcase", "testscript"})

class ArtifactService:
    def __init__(self, db: Session, storage: ArtifactStorage | None = None) -> None:
        self.db = db
        self.storage = storage or LocalArtifactStorage()

    def save_artifact(...):
        self._validate_kind(kind)
        clean_name = self._validate_name(name)
        self._validate_pipeline_run(project_id, pipeline_run_id)
        content_hash = hashlib.sha256(_content_to_bytes(content)).hexdigest()
        artifact = Artifact(project_id=project_id, pipeline_run_id=pipeline_run_id, kind=kind, name=clean_name, storage_path="pending", current_version=1)
        self.db.add(artifact)
        self.db.flush()
        storage_path = self.storage.write(project_id=project_id, artifact_id=artifact.id, version=1, name=clean_name, content=content)
        artifact.storage_path = storage_path
        artifact.versions.append(ArtifactVersion(version=1, content_hash=content_hash, storage_path=storage_path, created_by_user_id=owner_user_id))
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def create_version(...):
        next_version = artifact.current_version + 1
        content_hash = hashlib.sha256(_content_to_bytes(content)).hexdigest()
        storage_path = self.storage.write(project_id=artifact.project_id, artifact_id=artifact.id, version=next_version, name=artifact.name, content=content)
        artifact.current_version = next_version
        artifact.storage_path = storage_path
        artifact.versions.append(ArtifactVersion(version=next_version, content_hash=content_hash, storage_path=storage_path, created_by_user_id=created_by_user_id))
        self.db.commit()
        self.db.refresh(artifact)
        return artifact

    def list_artifacts(self, *, project_id: UUID, kind: str | None = None) -> list[Artifact]: ...
    def get_artifact(self, *, project_id: UUID, artifact_id: UUID) -> Artifact | None: ...
    def read_current_content(self, artifact: Artifact) -> bytes: return self.storage.read(artifact.storage_path)
```

### src/ai_qa/artifacts/storage.py

```python
class LocalArtifactStorage:
    def __init__(self, root: Path | str = Path("workspace") / "artifacts") -> None:
        self.root = Path(root).resolve()

    def write(...):
        safe_name = sanitize_artifact_name(name)
        storage_path = f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}"
        target_path = self._resolve_storage_path(storage_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_name(f".{target_path.name}.tmp.{uuid.uuid4().hex}")
        try:
            if isinstance(content, str): temp_path.write_text(content, encoding="utf-8")
            else: temp_path.write_bytes(content)
            temp_path.replace(target_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return storage_path

    def _resolve_storage_path(self, storage_path: str) -> Path:
        raw_path = Path(storage_path)
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise ValueError("Invalid artifact storage path")
        resolved = (self.root / raw_path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Artifact storage path escapes storage root")
        return resolved

def sanitize_artifact_name(name: str) -> str:
    candidate = Path(name.replace("\\", "/")).name.strip()
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip(".-_")
    if not candidate: candidate = "artifact"
    if len(candidate) > 180: ...
    return candidate
```

### Tests

Tests cover storage round-trip/traversal rejection/name sanitization, service metadata/version/hash/pipeline validation/commit cleanup, API member CRUD/versioning, binary base64, member/admin/outsider/unauthenticated/stale-user behavior, invalid kind/missing artifact/wrong pipeline project, and OpenAPI schema presence.
