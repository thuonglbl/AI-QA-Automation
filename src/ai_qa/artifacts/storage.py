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
        kind: str,
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
        kind: str,
        name: str,
        content: str | bytes,
    ) -> str:
        """Write content via temp file then atomic replace and return relative key."""
        safe_name = sanitize_artifact_name(name)
        storage_path = self._build_storage_path(project_id, artifact_id, version, kind, safe_name)
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
        self, project_id: UUID, artifact_id: UUID, version: int, kind: str, safe_name: str
    ) -> str:
        if kind == "requirements":
            return f"projects/{project_id}/requirement/{safe_name}"
        if kind == "raw_html":
            return f"projects/{project_id}/mcp/confluence/{safe_name}"
        return f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}"

    def _resolve_storage_path(self, storage_path: str) -> Path:
        raw_path = Path(storage_path)
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise ValueError("Invalid artifact storage path")

        resolved = (self.root / raw_path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Artifact storage path escapes storage root")
        return resolved


class S3ArtifactStorage:
    """S3/MinIO artifact storage backend."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool = False,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.bucket_name = bucket_name
        self.s3 = boto3.client(
            "s3",
            endpoint_url=f"{'https' if secure else 'http'}://{endpoint_url}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

    def write(
        self,
        *,
        project_id: UUID,
        artifact_id: UUID,
        version: int,
        kind: str,
        name: str,
        content: str | bytes,
    ) -> str:
        """Upload content to S3 bucket and return object key."""
        safe_name = sanitize_artifact_name(name)
        if kind == "requirements":
            object_key = f"projects/{project_id}/requirement/{safe_name}"
        elif kind == "raw_html":
            object_key = f"projects/{project_id}/mcp/confluence/{safe_name}"
        else:
            object_key = f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}"

        body = content.encode("utf-8") if isinstance(content, str) else content
        self.s3.put_object(Bucket=self.bucket_name, Key=object_key, Body=body)

        return object_key

    def read(self, storage_path: str) -> bytes:
        """Download content from S3 bucket."""
        from typing import cast

        response = self.s3.get_object(Bucket=self.bucket_name, Key=storage_path)
        return cast(bytes, response["Body"].read())

    def delete(self, storage_path: str) -> None:
        """Best-effort S3 object deletion."""
        try:
            self.s3.delete_object(Bucket=self.bucket_name, Key=storage_path)
        except Exception:
            pass


def sanitize_artifact_name(name: str) -> str:
    """Return a safe filename derived from untrusted artifact names.

    Supports subdirectory paths like 'page-id/raw.html' by sanitizing
    each path segment individually.
    """
    normalized = name.replace("\\", "/")
    parts = normalized.split("/")

    safe_parts = []
    for part in parts:
        part = part.strip()
        candidate = re.sub(r"[^A-Za-z0-9._-]+", "-", part).strip(".-_")
        if not candidate:
            continue
        if len(candidate) > 180:
            p = Path(candidate)
            suffix = p.suffix[:20]
            stem_limit = 180 - len(suffix)
            candidate = f"{p.stem[:stem_limit]}{suffix}"
        safe_parts.append(candidate)

    if not safe_parts:
        return "artifact"
    return "/".join(safe_parts)
