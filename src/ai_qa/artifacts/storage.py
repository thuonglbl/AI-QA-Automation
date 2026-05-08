"""Storage backends for project-scoped artifact content."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol
from uuid import UUID


class ArtifactStorage(Protocol):
    """Replaceable storage interface for artifact bytes."""

    def write(
        self,
        *,
        project_id: UUID,
        artifact_id: UUID,
        version: int,
        name: str,
        content: str | bytes,
    ) -> str:
        """Persist content and return an opaque storage path/key."""

    def read(self, storage_path: str) -> bytes:
        """Read previously persisted content by storage path/key."""

    def delete(self, storage_path: str) -> None:
        """Best-effort delete for cleanup after downstream failures."""


class LocalArtifactStorage:
    """Local filesystem artifact storage with traversal-safe deterministic keys."""

    def __init__(self, root: Path | str = Path("workspace") / "artifacts") -> None:
        self.root = Path(root).resolve()

    def write(
        self,
        *,
        project_id: UUID,
        artifact_id: UUID,
        version: int,
        name: str,
        content: str | bytes,
    ) -> str:
        """Write content via temp file then atomic replace and return relative key."""
        safe_name = sanitize_artifact_name(name)
        storage_path = self._build_storage_path(project_id, artifact_id, version, safe_name)
        target_path = self._resolve_storage_path(storage_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = target_path.with_name(f".{target_path.name}.tmp.{uuid.uuid4().hex}")
        try:
            if isinstance(content, str):
                temp_path.write_text(content, encoding="utf-8")
            else:
                temp_path.write_bytes(content)
            temp_path.replace(target_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        return storage_path

    def read(self, storage_path: str) -> bytes:
        """Read bytes from a stored artifact path after containment validation."""
        return self._resolve_storage_path(storage_path).read_bytes()

    def delete(self, storage_path: str) -> None:
        """Best-effort local file cleanup used when DB commit fails after write."""
        try:
            self._resolve_storage_path(storage_path).unlink(missing_ok=True)
        except OSError:
            return

    def _build_storage_path(
        self, project_id: UUID, artifact_id: UUID, version: int, safe_name: str
    ) -> str:
        return f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}"

    def _resolve_storage_path(self, storage_path: str) -> Path:
        raw_path = Path(storage_path)
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise ValueError("Invalid artifact storage path")

        resolved = (self.root / raw_path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Artifact storage path escapes storage root")
        return resolved


def sanitize_artifact_name(name: str) -> str:
    """Return a safe filename derived from untrusted artifact names."""
    candidate = Path(name.replace("\\", "/")).name.strip()
    candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", candidate).strip(".-_")
    if not candidate:
        candidate = "artifact"
    if len(candidate) > 180:
        path = Path(candidate)
        suffix = path.suffix[:20]
        stem_limit = 180 - len(suffix)
        candidate = f"{path.stem[:stem_limit]}{suffix}"
    return candidate
