"""Intent-level artifact adapter for project-scoped pipeline agents."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import StorageObjectNotFoundError
from ai_qa.db.models import Artifact
from ai_qa.pipelines.context import PipelineContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineArtifact:
    """Small DTO for artifact content consumed by pipeline agents."""

    id: UUID
    name: str
    kind: str
    content: str
    version: int
    source_type: str | None = None
    source_url: str | None = None
    warnings: list[dict[str, Any]] | None = None
    thread_id: UUID | None = None
    updated_at: datetime | None = None


def _sort_by_recency(items: list[PipelineArtifact]) -> list[PipelineArtifact]:
    """Order *items* most-recently-updated first.

    Artifacts loaded from the store always carry ``updated_at`` (tz-aware in
    production); any without one (e.g. hand-built test fixtures that never reach
    the store) sort last so a missing timestamp never raises during the comparison.
    """

    def _key(art: PipelineArtifact) -> datetime:
        dt = cast(datetime, art.updated_at)
        # SQLite round-trips drop tzinfo, so a dataset can mix freshly-set (aware)
        # and DB-read (naive) rows. Normalise naive→UTC so the compare never raises.
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)

    dated = [a for a in items if a.updated_at is not None]
    undated = [a for a in items if a.updated_at is None]
    dated.sort(key=_key, reverse=True)
    return dated + undated


class PipelineArtifactAdapter:
    """Translate pipeline intent into ArtifactService operations."""

    def __init__(self, context: PipelineContext) -> None:
        if context.artifact_service is None:
            raise ValueError("PipelineArtifactAdapter requires an ArtifactService")
        if context.project_id is None:
            raise ValueError("PipelineArtifactAdapter requires a bound project_id")
        self.context = context
        self.service: ArtifactService = context.artifact_service

    @property
    def project_id(self) -> UUID:
        assert self.context.project_id is not None
        return self.context.project_id

    def save_requirement_page(self, name: str, markdown: str) -> Artifact:
        """Persist an approved requirement page as project-scoped markdown content."""
        if not name.endswith(".md"):
            name += ".md"
        return self._save_text(kind="requirements", name=name, content=markdown)

    def save_requirement(
        self,
        *,
        page_id: str,
        markdown: str,
        source_type: str | None = None,
        source_url: str | None = None,
        warnings: list[dict[str, Any]] | None = None,
        title: str | None = None,
        parent_source_id: str | None = None,
        ancestor_source_ids: list[str] | None = None,
    ) -> Artifact:
        """Persist an APPROVED requirement under projects/{id}/requirements/ with provenance.

        Idempotent-by-name (D8): keeps a single approved artifact named ``{page_id}/requirement.md``
        per project. The new copy is saved FIRST (the per-artifact write is atomic), and only the
        superseded prior rows are deleted afterwards. This ordering preserves AC3 "no partial
        corruption": if the new save fails, the existing approved artifact is left intact rather
        than being deleted into a zero-row window.
        """
        name = f"{page_id}/requirement.md"

        # Snapshot any prior approved rows with the same name BEFORE saving the new copy.
        prior = [
            art
            for art in self.service.list_artifacts(project_id=self.project_id, kind="requirements")
            if art.name == name
        ]

        # Save the new approved copy first. If this raises, `prior` is untouched (no data loss).
        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind="requirements",
            name=name,
            content=markdown,
            source_type=source_type,
            source_url=source_url,
            warnings=warnings,
            title=title,
            parent_source_id=parent_source_id,
            ancestor_source_ids=ancestor_source_ids,
        )

        # Only after the new row is committed, remove the superseded prior rows (best-effort dedupe).
        for art in prior:
            try:
                self.service.delete_artifact(project_id=self.project_id, artifact_id=art.id)
            except Exception:
                logger.warning(
                    "save_requirement: could not delete superseded approved artifact %s — "
                    "leaving in place",
                    art.id,
                )

        self._schedule_change_event(artifact.id, "created")
        return artifact

    def delete_draft_requirement(self, page_id: str) -> bool:
        """Delete the pre-approval draft artifact for a page, if it exists.

        The draft is saved by `save_requirement_page` as ``{page_id}.md`` (no path separator).
        The approved copy uses ``{page_id}/requirement.md``.  Removing the draft after a
        successful approve keeps exactly one requirement artifact per page (D8).

        Always safe to call — returns ``False`` if no draft was found.  Never raises:
        any exception is logged as a warning and the caller continues normally.
        """
        draft_name = f"{page_id}.md"
        try:
            artifacts = self.service.list_artifacts(project_id=self.project_id, kind="requirements")
            for art in artifacts:
                if art.name == draft_name:
                    return self.service.delete_artifact(
                        project_id=self.project_id, artifact_id=art.id
                    )
            return False
        except Exception as exc:
            logger.warning(
                "delete_draft_requirement(%s): advisory deletion failed — %s", page_id, exc
            )
            return False

    def load_requirement_markdown(self) -> list[PipelineArtifact]:
        """Load all requirement markdown artifacts for the current project."""
        return self._load_text_artifacts(kind="requirements")

    def save_test_case(
        self,
        name: str,
        test_case: str | dict[str, Any],
        *,
        source_type: str | None = None,
        source_url: str | None = None,
        warnings: list[dict[str, Any]] | None = None,
        title: str | None = None,
    ) -> Artifact:
        """Persist an approved test case as stable JSON/text content.

        Idempotent-by-name (D8): keeps a single artifact per name. The new copy is saved
        FIRST (per-artifact write is atomic), then superseded prior rows are deleted
        (best-effort). This ordering preserves AC3 "no partial corruption": if the new
        save fails, existing artifacts are left intact rather than deleted into a zero-row
        window.
        """
        content = self._json_content(test_case)

        prior = [
            art
            for art in self.service.list_artifacts(project_id=self.project_id, kind="testcase")
            if art.name == name
        ]

        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind="testcase",
            name=name,
            content=content,
            source_type=source_type,
            source_url=source_url,
            warnings=warnings,
            title=title,
        )

        for art in prior:
            try:
                self.service.delete_artifact(project_id=self.project_id, artifact_id=art.id)
            except Exception:
                logger.warning(
                    "save_test_case: could not delete superseded artifact %s — leaving in place",
                    art.id,
                )

        self._schedule_change_event(artifact.id, "created")
        return artifact

    def load_test_cases(self) -> list[PipelineArtifact]:
        """Load approved test case artifacts for the current project (excludes drafts).

        Mary streams generation and saves each case immediately as a ``"draft"`` so the
        Test Cases folder fills live; those drafts are NOT approved yet and must be hidden
        from downstream stages until the user approves (approval re-saves the same name
        without the draft marker). ``source_type == "draft"`` is the discriminator.
        """
        return [a for a in self._load_text_artifacts(kind="testcase") if a.source_type != "draft"]

    def load_approved_test_cases(self) -> list[PipelineArtifact]:
        """Load approved test cases, prioritising the current thread.

        Excludes streaming ``"draft"`` test cases (saved live by Mary before approval);
        only approved copies feed Sarah.

        Artifacts whose ``thread_id`` matches ``context.thread_id`` are listed first
        (pre-select candidates for the selection panel); other project-level artifacts
        follow.  Within each group, the most-recently-updated test cases are listed
        first so that when Sarah is reached by skipping Mary (blank id at Bob), the
        previous session's / a colleague's freshest reusable work surfaces at the top.
        """
        artifacts = [
            a for a in self._load_text_artifacts(kind="testcase") if a.source_type != "draft"
        ]
        ctx_thread_id = self.context.thread_id
        current_thread: list[PipelineArtifact] = []
        other_threads: list[PipelineArtifact] = []
        for art in artifacts:
            if ctx_thread_id is not None and art.thread_id == ctx_thread_id:
                current_thread.append(art)
            else:
                other_threads.append(art)
        return _sort_by_recency(current_thread) + _sort_by_recency(other_threads)

    def save_script(self, name: str, script_content: str) -> Artifact:
        """Persist an APPROVED Playwright script under projects/{id}/test_scripts/.

        Idempotent-by-name (D8): keeps a single approved artifact per script name per
        project, so a reject→regenerate→re-approve (or a retried approve) converges to
        exactly one artifact instead of duplicating. The new copy is saved FIRST (the
        per-artifact write is atomic); the superseded prior rows are deleted afterwards
        so a mid-save failure never opens a zero-row window.

        save_script runs ONLY in the approve path — skip/reject/regenerate never call
        it — so every kind="playwright_script" artifact under test_scripts/ is approved
        by construction. Story 15.1 (load_approved_scripts) queries it project-scoped
        with no discriminator; skipped/rejected/regenerated scripts are never persisted.
        """
        prior = [
            art
            for art in self.service.list_artifacts(
                project_id=self.project_id, kind="playwright_script"
            )
            if art.name == name
        ]

        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind="playwright_script",
            name=name,
            content=script_content,
        )

        for art in prior:
            try:
                self.service.delete_artifact(project_id=self.project_id, artifact_id=art.id)
            except Exception:
                logger.warning(
                    "save_script: could not delete superseded approved artifact %s — "
                    "leaving in place",
                    art.id,
                )

        self._schedule_change_event(artifact.id, "created")
        return artifact

    def load_scripts(self) -> list[PipelineArtifact]:
        """Load all project-scoped Playwright script artifacts."""
        return self._load_text_artifacts(kind="playwright_script")

    def load_approved_scripts(self) -> list[PipelineArtifact]:
        """Load approved Playwright scripts, prioritising the current thread (Story 14.1).

        Every ``kind="playwright_script"`` artifact under ``test_scripts/`` is approved
        **by construction**: ``save_script`` runs only in Sarah's approve path
        (skip/reject/regenerate never persist a script — Story 13.8). So, unlike
        ``load_approved_test_cases`` (which filters ``source_type != "draft"`` because Mary
        streams pre-approval drafts), scripts have **no draft** and need **no discriminator
        filter**. This loader is therefore a thread-prioritised ``load_scripts()``.

        Artifacts whose ``thread_id`` matches ``context.thread_id`` are listed first
        (pre-select candidates for the selection panel); other project-level scripts
        follow. Within each group the original name-order from ``list_artifacts`` is
        preserved (stable sort).
        """
        artifacts = self._load_text_artifacts(kind="playwright_script")
        ctx_thread_id = self.context.thread_id
        current_thread: list[PipelineArtifact] = []
        other_threads: list[PipelineArtifact] = []
        for art in artifacts:
            if ctx_thread_id is not None and art.thread_id == ctx_thread_id:
                current_thread.append(art)
            else:
                other_threads.append(art)
        return current_thread + other_threads

    def save_metadata(self, name: str, metadata: dict[str, Any]) -> Artifact:
        """Persist metadata as a JSON configuration artifact.

        Idempotent-by-name (C43, mirrors the D8 pattern used by ``save_test_case`` /
        ``save_requirement``): keeps a single configuration artifact per name. The new
        copy is saved FIRST (the per-artifact write is atomic), then superseded prior
        same-name rows are deleted (best-effort). This prevents duplicate
        ``{filename}.metadata.json`` rows accumulating across reject→regen→re-approve
        cycles, so ``load_metadata`` never has to disambiguate between stale copies.
        """
        prior = [
            art
            for art in self.service.list_artifacts(project_id=self.project_id, kind="configuration")
            if art.name == name
        ]

        artifact = self._save_text(
            kind="configuration",
            name=name,
            content=json.dumps(metadata, indent=2, sort_keys=True, default=str),
        )

        for art in prior:
            try:
                self.service.delete_artifact(project_id=self.project_id, artifact_id=art.id)
            except Exception:
                logger.warning(
                    "save_metadata: could not delete superseded artifact %s — leaving in place",
                    art.id,
                )

        return artifact

    def load_metadata(self, name: str) -> dict[str, Any] | None:
        """Load a JSON configuration artifact by name. None if absent/unparseable."""
        for art in self._load_text_artifacts(kind="configuration"):
            if art.name == name:
                try:
                    parsed = json.loads(art.content)
                except json.JSONDecodeError, ValueError:
                    return None
                return parsed if isinstance(parsed, dict) else None
        return None

    def load_all_metadata(self) -> dict[str, dict[str, Any]]:
        """Load every JSON configuration artifact once as a ``name -> parsed-dict`` map.

        Bulk alternative to calling :meth:`load_metadata` per name (which re-lists and
        decodes all configuration artifacts on each call — O(names x artifacts)). Skips
        unparseable or non-dict entries.
        """
        out: dict[str, dict[str, Any]] = {}
        for art in self._load_text_artifacts(kind="configuration"):
            try:
                parsed = json.loads(art.content)
            except json.JSONDecodeError, ValueError:
                continue
            if isinstance(parsed, dict):
                out[art.name] = parsed
        return out

    def save_image(self, name: str, image_bytes: bytes) -> Artifact:
        """Persist a downloaded image artifact."""
        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind="image",
            name=name,
            content=image_bytes,
        )
        self._schedule_change_event(artifact.id, "created")
        return artifact

    def save_execution_output(
        self,
        *,
        run_id: UUID,
        file_name: str,
        content: str | bytes,
        kind: str,
        prefix: str = "runs",
    ) -> Artifact:
        """Persist one execution output under the logical ``{prefix}/{run_id}/{file}`` (14.3).

        The physical storage key is derived by ``build_artifact_key`` from ``kind`` (the
        execution kinds fall into the ``artifacts/`` catch-all); ``prefix`` only governs
        the logical/browse name. ``prefix`` is re-validated here (runtime guard, AC2) so a
        misconfiguration fails before output is lost. Binary blobs (screenshots/traces) use
        the ``bytes`` content path; report/log use text.
        """
        from ai_qa.config import validate_execution_output_prefix

        clean_prefix = validate_execution_output_prefix(prefix)
        logical_name = f"{clean_prefix}/{run_id}/{file_name}"
        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=run_id,
            thread_id=self.context.thread_id,
            kind=kind,
            name=logical_name,
            content=content,
        )
        self._schedule_change_event(artifact.id, "created")
        return artifact

    def persist_run_outputs(
        self,
        *,
        run_id: UUID,
        files: list[tuple[str, str | bytes, str]],
        prefix: str = "runs",
        overwrite: bool = False,
    ) -> list[UUID]:
        """Persist a batch of execution outputs for one run; return the artifact ids (14.3).

        AC3 uniqueness/overwrite guard: if any artifact already exists under
        ``{prefix}/{run_id}/`` and ``overwrite`` is False, raise (a fresh run id makes
        this a no-op; the guard protects re-runs that reuse an id). The guard is checked
        ONCE for the batch — the per-run folder is shared by all files of the run.
        """
        from ai_qa.config import validate_execution_output_prefix

        clean_prefix = validate_execution_output_prefix(prefix)
        if not overwrite and self._execution_outputs_exist(clean_prefix, run_id):
            raise ValueError(
                f"Execution outputs already exist for run {run_id} and overwrite is disabled."
            )
        ids: list[UUID] = []
        for file_name, content, kind in files:
            artifact = self.save_execution_output(
                run_id=run_id,
                file_name=file_name,
                content=content,
                kind=kind,
                prefix=clean_prefix,
            )
            ids.append(artifact.id)
        return ids

    def _execution_outputs_exist(self, prefix: str, run_id: UUID) -> bool:
        """True if any artifact already lives under the run's logical prefix."""
        needle = f"{prefix}/{run_id}/"
        artifacts = self.service.list_artifacts(project_id=self.project_id)
        return any(a.name.startswith(needle) for a in artifacts)

    def _save_text(self, *, kind: str, name: str, content: str) -> Artifact:
        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind=kind,
            name=name,
            content=content,
        )
        self._schedule_change_event(artifact.id, "created")
        return artifact

    def _schedule_change_event(self, artifact_id: UUID, change_type: str) -> None:
        """Schedule a fire-and-forget broadcast on the running event loop, if any.

        This method is always called from synchronous code (adapter is sync), but
        the adapter's callers (handle_start / handle_approve) are async, so a live
        event loop is present at runtime.  create_task() schedules the coroutine
        without blocking the sync caller.

        When called from a unit test that runs the adapter directly outside an async
        context, get_running_loop() raises RuntimeError — that is caught and ignored,
        which is the correct behaviour (no loop == no broadcast needed in tests).
        """
        import asyncio

        # Lazy import prevents circular import at module load time.
        from ai_qa.api.websocket import broadcast_artifact_change  # noqa: PLC0415

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                broadcast_artifact_change(
                    project_id=str(self.project_id),
                    artifact_id=str(artifact_id),
                    change_type=change_type,
                )
            )
        except RuntimeError:
            # No running loop: unit test calling adapter directly — silent skip.
            pass

    def _load_text_artifacts(self, *, kind: str) -> list[PipelineArtifact]:
        artifacts = self.service.list_artifacts(project_id=self.project_id, kind=kind)
        loaded: list[PipelineArtifact] = []
        for artifact in artifacts:
            try:
                loaded.append(self._to_pipeline_artifact(artifact))
            except StorageObjectNotFoundError:
                # An artifact row whose backing object is gone (e.g. deleted on the
                # filesystem) must not abort the whole load — skip it so the surviving
                # artifacts (and the agents that read them, e.g. Bob's resume step)
                # keep working. Other storage errors propagate.
                logger.warning(
                    "Skipping artifact with missing storage object: "
                    "id=%s kind=%s name=%s storage_path=%s",
                    artifact.id,
                    artifact.kind,
                    artifact.name,
                    artifact.storage_path,
                )
        return loaded

    def _to_pipeline_artifact(self, artifact: Artifact) -> PipelineArtifact:
        content_bytes = self.service.read_current_content(artifact)
        return PipelineArtifact(
            id=artifact.id,
            name=artifact.name,
            kind=artifact.kind,
            content=content_bytes.decode("utf-8"),
            version=artifact.current_version,
            source_type=artifact.source_type,
            source_url=artifact.source_url,
            warnings=artifact.warnings,
            thread_id=artifact.thread_id,
            updated_at=artifact.updated_at,
        )

    def _json_content(self, value: str | dict[str, Any]) -> str:
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2, sort_keys=True, default=str)
