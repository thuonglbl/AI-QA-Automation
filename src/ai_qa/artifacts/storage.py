"""Storage backends for project-scoped artifact content."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol
from uuid import UUID


def build_artifact_key(
    *,
    project_id: UUID,
    artifact_id: UUID,
    version: int,
    kind: str,
    safe_name: str,
) -> str:
    """Return the canonical object-storage key for an artifact write.

    Collision-safe nested keys: every artifact and version gets its own path
    under a logical folder, so two distinct artifacts never share a key and each
    version's bytes are retained.  The logical folders
    (``requirements``/``test_cases``/``test_scripts``) remain browsable by prefix
    for empty-folder projection (Story 10.2).
    """
    if kind == "raw_html":
        folder = "requirements/mcp/confluence"
    elif kind == "requirements":
        folder = "requirements"
    elif kind == "testcase":
        folder = "test_cases"
    elif kind in ("testscript", "playwright_script"):
        folder = "test_scripts"
    else:
        folder = "artifacts"
    return f"projects/{project_id}/{folder}/{artifact_id}/v{version}/{safe_name}"


def folder_for_kind(kind: str, name: str = "") -> str:
    """Return the canonical browse-folder name for the given artifact kind.

    This is the **browse** classifier used by the UI to group artifacts into
    logical folders.  It is intentionally distinct from ``build_artifact_key``
    (the *storage* key builder) so that the catch-all label here is "reports"
    while the storage catch-all prefix remains "artifacts/".  Do **not** wire
    this function into ``build_artifact_key`` — their catch-alls diverge by design.

    The optional ``name`` lets the classifier route by filename when the kind
    alone is ambiguous (the requirement metadata sidecar is ``configuration`` but
    belongs with its requirement, not in reports).

    Returns one of: ``"requirements"``, ``"test_cases"``, ``"test_scripts"``, ``"reports"``.
    """
    # Requirement-domain assets all browse under "requirements"; the frontend
    # then tucks the non-`.md` ones into a "raw" subfolder. raw_html (page HTML +
    # url sidecar) and the page images/screenshots are raw companions of the MD;
    # the requirement metadata sidecar (kind=configuration) rides along by name.
    if kind in ("requirements", "raw_html", "image", "screenshot"):
        return "requirements"
    if kind == "configuration" and "requirement.metadata" in name:
        return "requirements"
    if kind == "testcase":
        return "test_cases"
    if kind in ("testscript", "playwright_script"):
        return "test_scripts"
    # Story 14.3: execution outputs browse under "reports" (explicit, though the
    # catch-all below already returns it — keeps intent clear next to the others).
    if kind in ("report", "trace", "log", "execution_screenshot"):
        return "reports"
    # catch-all: markdown, mermaid, other configuration (e.g. mary_selected_id.json)
    return "reports"


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

    def delete_prefix(self, prefix: str) -> None:
        """Delete all objects under the given key prefix (project cleanup)."""


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

    def delete_prefix(self, prefix: str) -> None:
        """Delete all files under the given prefix (project cleanup)."""
        import logging
        import shutil

        logger = logging.getLogger(__name__)
        try:
            target = self._resolve_storage_path(prefix)
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
                logger.info("Local storage cleanup for prefix '%s': removed directory", prefix)
            elif target.is_file():
                target.unlink(missing_ok=True)
                logger.info("Local storage cleanup for prefix '%s': removed file", prefix)
        except (ValueError, OSError) as exc:
            logger.warning("Local storage cleanup failed for prefix '%s': %s", prefix, exc)

    def _build_storage_path(
        self, project_id: UUID, artifact_id: UUID, version: int, kind: str, safe_name: str
    ) -> str:
        return build_artifact_key(
            project_id=project_id,
            artifact_id=artifact_id,
            version=version,
            kind=kind,
            safe_name=safe_name,
        )

    def _resolve_storage_path(self, storage_path: str) -> Path:
        raw_path = Path(storage_path)
        if raw_path.is_absolute() or ".." in raw_path.parts:
            raise ValueError("Invalid artifact storage path")

        resolved = (self.root / raw_path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Artifact storage path escapes storage root")
        return resolved


class S3ArtifactStorage:
    """S3/SeaweedFS artifact storage backend."""

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
        object_key = build_artifact_key(
            project_id=project_id,
            artifact_id=artifact_id,
            version=version,
            kind=kind,
            safe_name=safe_name,
        )
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

    def delete_prefix(self, prefix: str) -> None:
        """Delete all S3 objects under the given key prefix (project cleanup)."""
        import logging

        logger = logging.getLogger(__name__)
        try:
            paginator = self.s3.get_paginator("list_objects_v2")
            total_deleted = 0
            for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix):
                objects = page.get("Contents", [])
                if objects:
                    self.s3.delete_objects(
                        Bucket=self.bucket_name,
                        Delete={"Objects": [{"Key": obj["Key"]} for obj in objects]},
                    )
                    total_deleted += len(objects)
            # Also try to delete the prefix itself as a directory object
            try:
                self.s3.delete_object(Bucket=self.bucket_name, Key=prefix)
                self.s3.delete_object(Bucket=self.bucket_name, Key=prefix.rstrip("/"))
            except Exception:
                pass
            logger.info(
                "Storage cleanup for prefix '%s': deleted %d objects", prefix, total_deleted
            )
        except Exception as exc:
            logger.warning("Storage cleanup failed for prefix '%s': %s", prefix, exc)


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


def role_to_folder(role: str | None) -> str:
    """Map an application role to a single artifact sub-folder segment (no slashes).

    Returns ``""`` when the role is ``None``/blank so the artifact lands at the folder
    root. Spaces collapse to underscores and any path separators are stripped, keeping the
    per-role sub-folder one level deep (e.g. ``Admin`` → ``Admin``, ``Admin User`` →
    ``Admin_User``). Shared by Mary (``<role>/<case>.md``) and Sarah (``<role>/<script>.py``)
    so a role's test cases and its scripts land under the SAME folder name.
    """
    if not role or not role.strip():
        return ""
    cleaned = re.sub(r"[\\/]+", " ", role.strip())
    return re.sub(r"\s+", "_", cleaned)
