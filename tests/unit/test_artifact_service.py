"""Tests for project-scoped artifact storage and service behavior."""

from collections.abc import Generator
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.artifacts.service import ARTIFACT_KINDS, REQUIRED_ARTIFACT_FOLDERS, ArtifactService
from ai_qa.artifacts.storage import (
    LocalArtifactStorage,
    S3ArtifactStorage,
    StorageObjectNotFoundError,
    build_artifact_key,
    folder_for_kind,
    sanitize_artifact_name,
)
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, User
from ai_qa.threads.models import AgentRun, Thread


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                User.__table__,
                Project.__table__,
                Thread.__table__,
                AgentRun.__table__,
                Artifact.__table__,
                ArtifactVersion.__table__,
            ],
        ),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
    engine.dispose()


def _create_project(session: Session) -> Project:
    project = Project(name="Scoped", description="Project scoped artifacts")
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_local_storage_sanitizes_paths_and_round_trips_content(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)
    project_id = uuid4()
    artifact_id = uuid4()

    storage_path = storage.write(
        project_id=project_id,
        artifact_id=artifact_id,
        version=1,
        kind="markdown",
        name="..\\secret folder/unsafe script.md",
        content="hello artifact",
    )

    assert ".." not in Path(storage_path).parts
    assert storage_path.endswith("unsafe-script.md")
    assert storage.read(storage_path) == b"hello artifact"


def test_local_storage_rejects_traversal_reads(tmp_path: Path) -> None:
    storage = LocalArtifactStorage(tmp_path)

    with pytest.raises(ValueError, match="Invalid artifact storage path"):
        storage.read("../secret.txt")

    with pytest.raises(ValueError, match="Invalid artifact storage path"):
        storage.read(str((tmp_path / "absolute.txt").resolve()))


def test_sanitize_artifact_name_handles_blank_and_windows_separators() -> None:
    assert (
        sanitize_artifact_name("..\\folder\\Playwright Script!.ts")
        == "folder/Playwright-Script-.ts"
    )
    assert sanitize_artifact_name("../") == "artifact"


def test_artifact_service_persists_metadata_initial_version_and_hash(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="requirements.md",
        content="# Requirements",
    )

    assert artifact.project_id == project.id
    assert artifact.kind == "markdown"
    assert artifact.current_version == 1
    assert artifact.storage_path.endswith("requirements.md")
    assert service.read_current_content(artifact) == b"# Requirements"

    versions = db_session.execute(select(ArtifactVersion)).scalars().all()
    assert len(versions) == 1
    assert versions[0].version == 1
    assert len(versions[0].content_hash) == 64
    assert versions[0].storage_path == artifact.storage_path


def test_artifact_service_appends_versions_without_mutating_history(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="mermaid",
        name="flow.mmd",
        content="graph TD; A-->B;",
    )
    first_storage_path = artifact.storage_path
    first_hash = artifact.versions[0].content_hash

    updated = service.create_version(
        project_id=project.id,
        artifact_id=artifact.id,
        created_by_user_id=None,
        content="graph TD; A-->C;",
    )

    assert updated is not None
    assert updated.current_version == 2
    assert updated.storage_path != first_storage_path
    assert service.read_current_content(updated) == b"graph TD; A-->C;"
    assert service.storage.read(first_storage_path) == b"graph TD; A-->B;"

    versions = sorted(updated.versions, key=lambda version: version.version)
    assert [version.version for version in versions] == [1, 2]
    assert versions[0].storage_path == first_storage_path
    assert versions[0].content_hash == first_hash
    assert versions[1].content_hash != first_hash


def test_artifact_service_filters_kind_and_validates_pipeline_project(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    other_project = Project(name="Other")
    db_session.add(other_project)
    db_session.commit()
    user = User(
        email="test@test.com",
        display_name="test",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    thread = Thread(project_id=other_project.id, user_id=user.id)
    db_session.add(thread)
    db_session.flush()
    agent_run = AgentRun(thread_id=thread.id, status="pending")
    db_session.add(agent_run)
    db_session.commit()
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="one.md",
        content="one",
    )
    service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="report",
        name="report.md",
        content="report",
    )

    assert [artifact.name for artifact in service.list_artifacts(project_id=project.id)] == [
        "one.md",
        "report.md",
    ]
    assert [
        artifact.name for artifact in service.list_artifacts(project_id=project.id, kind="report")
    ] == ["report.md"]
    with pytest.raises(ValueError, match="Agent run does not belong to project"):
        service.save_artifact(
            project_id=project.id,
            owner_user_id=None,
            kind="markdown",
            name="bad.md",
            content="bad",
            agent_run_id=agent_run.id,
        )


class RecordingStorage:
    """Storage fake that records writes and deletes for rollback cleanup tests."""

    def __init__(self) -> None:
        self.contents: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def write(
        self,
        *,
        project_id: object,
        artifact_id: object,
        version: int,
        kind: str,
        name: str,
        content: str | bytes,
    ) -> str:
        storage_path = f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{name}"
        self.contents[storage_path] = (
            content.encode("utf-8") if isinstance(content, str) else content
        )
        return storage_path

    def read(self, storage_path: str) -> bytes:
        return self.contents[storage_path]

    def delete(self, storage_path: str) -> None:
        self.deleted.append(storage_path)
        self.contents.pop(storage_path, None)

    def delete_prefix(self, prefix: str) -> None:
        """Remove all stored objects whose key starts with prefix."""
        to_remove = [k for k in self.contents if k.startswith(prefix)]
        for k in to_remove:
            self.deleted.append(k)
            del self.contents[k]


def test_artifact_service_cleans_file_when_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(db_session)
    storage = RecordingStorage()
    service = ArtifactService(db_session, storage)

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        service.save_artifact(
            project_id=project.id,
            owner_user_id=None,
            kind="markdown",
            name="cleanup.md",
            content="cleanup",
        )

    assert len(storage.deleted) == 1
    assert storage.contents == {}


def test_artifact_service_cleans_version_file_when_commit_fails(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _create_project(db_session)
    storage = RecordingStorage()
    service = ArtifactService(db_session, storage)
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="version-cleanup.md",
        content="v1",
    )
    first_storage_path = artifact.storage_path

    def fail_commit() -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(RuntimeError, match="commit failed"):
        service.create_version(
            project_id=project.id,
            artifact_id=artifact.id,
            created_by_user_id=None,
            content="v2",
        )

    assert len(storage.deleted) == 1
    assert first_storage_path in storage.contents
    assert all("/v2/" not in path for path in storage.contents)


def test_artifact_service_create_version_is_project_scoped(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    other_project = Project(name="Other")
    db_session.add(other_project)
    db_session.commit()
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="scoped.md",
        content="v1",
    )

    updated = service.create_version(
        project_id=other_project.id,
        artifact_id=artifact.id,
        created_by_user_id=None,
        content="v2",
    )

    assert updated is None


def test_artifact_service_delete_artifact_cascades_and_cleans_storage(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    storage = RecordingStorage()
    service = ArtifactService(db_session, storage)

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="to_delete.md",
        content="v1",
    )
    service.create_version(
        project_id=project.id,
        artifact_id=artifact.id,
        created_by_user_id=None,
        content="v2",
    )

    # Verify metadata and storage pre-delete
    storage_paths = list(storage.contents.keys())
    assert len(storage_paths) == 2

    # Delete the artifact
    deleted = service.delete_artifact(project_id=project.id, artifact_id=artifact.id)
    assert deleted is True

    # Verify metadata cascade
    assert service.get_artifact(project_id=project.id, artifact_id=artifact.id) is None
    versions = (
        db_session.execute(
            select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact.id)
        )
        .scalars()
        .all()
    )
    assert len(versions) == 0

    # Verify storage cleanup
    assert len(storage.contents) == 0
    for path in storage_paths:
        assert path in storage.deleted


def test_artifact_service_delete_artifact_is_project_scoped(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    other_project = Project(name="Other")
    db_session.add(other_project)
    db_session.commit()
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="markdown",
        name="scoped.md",
        content="v1",
    )

    deleted = service.delete_artifact(project_id=other_project.id, artifact_id=artifact.id)
    assert deleted is False

    # Still exists in original project
    assert service.get_artifact(project_id=project.id, artifact_id=artifact.id) is not None


# ---------------------------------------------------------------------------
# NEW TESTS — Task 5.2 additions
# ---------------------------------------------------------------------------


# Canonical kind -> logical folder. Generic kinds live under "artifacts".
_EXPECTED_FOLDERS = {
    "requirements": "requirements",
    "raw_html": "requirements/mcp/confluence",
    "testcase": "test_cases",
    "testscript": "test_scripts",
    "playwright_script": "test_scripts",
    "configuration": "artifacts",
    "image": "artifacts",
    "markdown": "artifacts",
    "mermaid": "artifacts",
    "report": "artifacts",
    "screenshot": "artifacts",
    # Story 14.3 execution kinds — storage catch-all is "artifacts/".
    "trace": "artifacts",
    "log": "artifacts",
    "execution_screenshot": "artifacts",
    "video": "artifacts",
}


class _CapturingS3:
    """Minimal S3 client stand-in that records the object key written."""

    def __init__(self) -> None:
        self.last_key: str | None = None

    def put_object(self, *, Bucket: str, Key: str, Body: bytes) -> None:  # noqa: N803
        self.last_key = Key


def test_build_artifact_key_covers_every_kind_with_collision_safe_nesting() -> None:
    """Every kind maps to a nested per-artifact/per-version key under its folder.

    The expected-folder table is asserted to match ARTIFACT_KINDS, so a newly
    added kind without a mapping entry fails here instead of silently going
    uncovered.
    """
    assert set(_EXPECTED_FOLDERS) == set(ARTIFACT_KINDS)

    pid = uuid4()
    aid = uuid4()
    for kind, folder in _EXPECTED_FOLDERS.items():
        key = build_artifact_key(
            project_id=pid, artifact_id=aid, version=3, kind=kind, safe_name="file.bin"
        )
        assert key == f"projects/{pid}/{folder}/{aid}/v3/file.bin", f"kind={kind}"


def test_both_backends_route_through_build_artifact_key(tmp_path: Path) -> None:
    """Local and S3 backends must derive their key from the shared helper."""
    pid = uuid4()
    aid = uuid4()
    expected = build_artifact_key(
        project_id=pid, artifact_id=aid, version=1, kind="testcase", safe_name="cases.json"
    )

    local = LocalArtifactStorage(tmp_path)
    local_key = local.write(
        project_id=pid, artifact_id=aid, version=1, kind="testcase", name="cases.json", content="{}"
    )
    assert local_key == expected

    s3 = S3ArtifactStorage("localhost:8333", "key", "secret", "bucket")
    s3.s3 = _CapturingS3()
    s3_key = s3.write(
        project_id=pid, artifact_id=aid, version=1, kind="testcase", name="cases.json", content="{}"
    )
    assert s3_key == expected
    assert s3.s3.last_key == expected


def test_local_storage_testcase_lands_under_test_cases(tmp_path: Path) -> None:
    """New kind→folder mapping is applied by LocalArtifactStorage."""
    storage = LocalArtifactStorage(tmp_path)
    pid = uuid4()
    aid = uuid4()
    path = storage.write(
        project_id=pid, artifact_id=aid, version=1, kind="testcase", name="cases.json", content="{}"
    )
    assert path.startswith(f"projects/{pid}/test_cases/")
    assert storage.read(path) == b"{}"


def test_local_storage_testscript_and_playwright_script_land_under_test_scripts(
    tmp_path: Path,
) -> None:
    """testscript and playwright_script both land under test_scripts/."""
    storage = LocalArtifactStorage(tmp_path)
    pid = uuid4()
    aid = uuid4()
    for kind in ("testscript", "playwright_script"):
        path = storage.write(
            project_id=pid, artifact_id=aid, version=1, kind=kind, name="script.py", content="pass"
        )
        assert path.startswith(f"projects/{pid}/test_scripts/"), f"kind={kind}"


def test_required_folders_returns_three_prefixes(db_session: Session, tmp_path: Path) -> None:
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))
    folders = service.required_folders(project.id)
    assert len(folders) == 3
    assert f"projects/{project.id}/requirements/" in folders
    assert f"projects/{project.id}/test_cases/" in folders
    assert f"projects/{project.id}/test_scripts/" in folders
    # Constant is consistent with what the method returns
    for folder_name in REQUIRED_ARTIFACT_FOLDERS:
        assert any(folder_name in f for f in folders)


def test_artifact_service_persists_creator_updater_and_thread(
    db_session: Session, tmp_path: Path
) -> None:
    """creator, updater, and thread_id are set on create and version."""
    project = _create_project(db_session)
    user = User(
        email="owner@example.com",
        display_name="Owner",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    thread = Thread(project_id=project.id, user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=user.id,
        kind="markdown",
        name="owned.md",
        content="v1",
        thread_id=thread.id,
    )

    assert artifact.created_by_user_id == user.id
    assert artifact.updated_by_user_id == user.id
    assert artifact.thread_id == thread.id

    editor = User(
        email="editor@example.com",
        display_name="Editor",
        role="user",
        is_active=True,
    )
    db_session.add(editor)
    db_session.commit()

    updated = service.create_version(
        project_id=project.id,
        artifact_id=artifact.id,
        created_by_user_id=editor.id,
        content="v2",
    )

    assert updated is not None
    assert updated.created_by_user_id == user.id  # unchanged
    assert updated.updated_by_user_id == editor.id  # set to editor
    assert updated.thread_id == thread.id  # unchanged


def test_artifact_service_rejects_thread_from_different_project(
    db_session: Session, tmp_path: Path
) -> None:
    project = _create_project(db_session)
    other_project = Project(name="Other")
    db_session.add(other_project)
    user = User(
        email="u@example.com",
        display_name="U",
        role="user",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    other_thread = Thread(project_id=other_project.id, user_id=user.id)
    db_session.add(other_thread)
    db_session.commit()

    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    with pytest.raises(ValueError, match="Thread does not belong to project"):
        service.save_artifact(
            project_id=project.id,
            owner_user_id=None,
            kind="markdown",
            name="bad.md",
            content="bad",
            thread_id=other_thread.id,
        )


# ---------------------------------------------------------------------------
# Task 5.2 — folder_for_kind + list_artifact_tree tests
# ---------------------------------------------------------------------------


# --- folder_for_kind exhaustive coverage ---


def test_folder_for_kind_covers_every_artifact_kind() -> None:
    """folder_for_kind returns a non-empty string for every registered kind."""
    valid_folders = {"requirements", "test_cases", "test_scripts", "reports"}
    for kind in ARTIFACT_KINDS:
        result = folder_for_kind(kind)
        assert result in valid_folders, f"Unexpected folder '{result}' for kind '{kind}'"


def test_folder_for_kind_named_kind_mapping() -> None:
    """Spot-check the canonical named-kind → browse-folder assignments."""
    assert folder_for_kind("requirements") == "requirements"
    assert folder_for_kind("raw_html") == "requirements"
    # Page images/screenshots are raw companions of a requirement → requirements folder.
    assert folder_for_kind("image") == "requirements"
    assert folder_for_kind("screenshot") == "requirements"
    assert folder_for_kind("testcase") == "test_cases"
    assert folder_for_kind("testscript") == "test_scripts"
    assert folder_for_kind("playwright_script") == "test_scripts"


def test_folder_for_kind_requirement_metadata_sidecar_routes_to_requirements() -> None:
    """The requirement metadata sidecar is kind=configuration but belongs with its
    requirement, routed by name; other configuration (e.g. mary_selected_id) stays in reports."""
    assert folder_for_kind("configuration", "1234/requirement.metadata.json") == "requirements"
    assert folder_for_kind("configuration", "mary_selected_id.json") == "reports"
    assert folder_for_kind("configuration") == "reports"


def test_folder_for_kind_catch_all_is_reports() -> None:
    """Kinds not in named groups route to the 'reports' catch-all."""
    for kind in ("report", "markdown", "mermaid", "configuration"):
        assert folder_for_kind(kind) == "reports", f"Expected 'reports' for kind '{kind}'"


def test_folder_for_kind_execution_kinds_route_to_reports() -> None:
    """Story 14.3: execution outputs browse under 'reports'."""
    for kind in ("trace", "log", "execution_screenshot", "video"):
        assert folder_for_kind(kind) == "reports", f"Expected 'reports' for kind '{kind}'"


def test_execution_kinds_are_registered() -> None:
    """Story 14.3: the new execution kinds are accepted by ARTIFACT_KINDS."""
    assert {"trace", "log", "execution_screenshot", "video"} <= ARTIFACT_KINDS


def test_folder_for_kind_unknown_kind_returns_reports() -> None:
    """Unknown / future kinds are routed to 'reports' by the catch-all."""
    assert folder_for_kind("unknown_future_kind") == "reports"


def test_folder_for_kind_agrees_with_build_artifact_key_on_named_kinds() -> None:
    """Task 1.2 agreement check: browse folder name must appear in the storage key
    for the 5 named kinds (requirements, raw_html, testcase, testscript, playwright_script).
    This verifies Task 1.2 — they diverge intentionally on the catch-all,
    so only check the named ones.
    """
    named_agreement = {
        "requirements": "requirements",
        "raw_html": "requirements",
        "testcase": "test_cases",
        "testscript": "test_scripts",
        "playwright_script": "test_scripts",
    }
    pid = uuid4()
    aid = uuid4()
    for kind, expected_browse_folder in named_agreement.items():
        storage_key = build_artifact_key(
            project_id=pid, artifact_id=aid, version=1, kind=kind, safe_name="f.bin"
        )
        browse_folder = folder_for_kind(kind)
        assert browse_folder == expected_browse_folder, f"kind={kind}: browse={browse_folder}"
        # storage key must contain the same browse folder prefix (just the first segment)
        browse_top = expected_browse_folder.split("/")[0]  # e.g. "requirements" or "test_cases"
        assert browse_top in storage_key, (
            f"Storage key '{storage_key}' does not contain browse segment '{browse_top}'"
        )


# --- list_artifact_tree unit tests ---


def _make_user(session: Session, *, email: str, display_name: str) -> User:
    u = User(
        email=email,
        display_name=display_name,
        role="standard",
        is_active=True,
    )
    session.add(u)
    session.commit()
    return u


def test_list_artifact_tree_empty_project_returns_four_folders(
    db_session: Session, tmp_path: Path
) -> None:
    """Empty project returns all 4 browse folders; the 3 required ones are marked required=True."""
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    folders = service.list_artifact_tree(project_id=project.id)

    folder_names = [f["name"] for f in folders]
    assert folder_names == ["requirements", "test_cases", "test_scripts", "reports"]

    for folder in folders:
        assert folder["is_empty"] is True
        assert folder["entries"] == []

    required_names = {f["name"] for f in folders if f["required"]}
    assert required_names == {"requirements", "test_cases", "test_scripts"}

    # Reports is NOT required by the story (catch-all bucket only)
    reports = next(f for f in folders if f["name"] == "reports")
    assert reports["required"] is False


def test_list_artifact_tree_groups_artifacts_correctly(db_session: Session, tmp_path: Path) -> None:
    """Artifacts land in the correct browse folder by kind."""
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    # requirements bucket
    service.save_artifact(
        project_id=project.id, owner_user_id=None, kind="requirements", name="req.md", content="r"
    )
    service.save_artifact(
        project_id=project.id, owner_user_id=None, kind="raw_html", name="page.html", content="<h>"
    )
    # test_cases bucket
    service.save_artifact(
        project_id=project.id, owner_user_id=None, kind="testcase", name="tc.json", content="{}"
    )
    # test_scripts bucket
    service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="playwright_script",
        name="pw.ts",
        content="t",
    )
    # page image is a raw companion of a requirement → requirements bucket
    service.save_artifact(
        project_id=project.id, owner_user_id=None, kind="image", name="img.png", content="..."
    )
    # reports (catch-all) bucket
    service.save_artifact(
        project_id=project.id, owner_user_id=None, kind="report", name="rep.md", content="rep"
    )

    folders = service.list_artifact_tree(project_id=project.id)
    folder_map = {f["name"]: f for f in folders}

    req_names = {e["name"] for e in folder_map["requirements"]["entries"]}
    assert req_names == {"req.md", "page.html", "img.png"}

    tc_names = {e["name"] for e in folder_map["test_cases"]["entries"]}
    assert tc_names == {"tc.json"}

    ts_names = {e["name"] for e in folder_map["test_scripts"]["entries"]}
    assert ts_names == {"pw.ts"}

    report_names = {e["name"] for e in folder_map["reports"]["entries"]}
    assert report_names == {"rep.md"}

    # is_empty flags match actual content
    assert folder_map["requirements"]["is_empty"] is False
    assert folder_map["test_cases"]["is_empty"] is False
    assert folder_map["test_scripts"]["is_empty"] is False
    assert folder_map["reports"]["is_empty"] is False


def test_save_artifact_persists_title_and_parent_and_surfaces_in_tree(
    db_session: Session, tmp_path: Path
) -> None:
    """title + parent_source_id round-trip through save_artifact and the browse tree
    so the frontend can show friendly names and build a Confluence-like hierarchy."""
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    root = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="requirements",
        name="100/requirement.md",
        content="# Root",
        title="Personal Travel Plan",
        parent_source_id=None,
    )
    child = service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="requirements",
        name="101/requirement.md",
        content="# Child",
        title="US01 - Create journey",
        parent_source_id="100",
    )

    assert root.title == "Personal Travel Plan"
    assert root.parent_source_id is None
    assert child.title == "US01 - Create journey"
    assert child.parent_source_id == "100"

    folders = {f["name"]: f for f in service.list_artifact_tree(project_id=project.id)}
    by_name = {e["name"]: e for e in folders["requirements"]["entries"]}
    assert by_name["100/requirement.md"]["title"] == "Personal Travel Plan"
    assert by_name["100/requirement.md"]["parent_source_id"] is None
    assert by_name["101/requirement.md"]["title"] == "US01 - Create journey"
    assert by_name["101/requirement.md"]["parent_source_id"] == "100"


def test_list_artifact_tree_resolves_display_names(db_session: Session, tmp_path: Path) -> None:
    """Entries carry resolved creator/updater display names — not UUIDs."""
    project = _create_project(db_session)
    creator = _make_user(db_session, email="creator@x.com", display_name="Alice Creator")
    editor = _make_user(db_session, email="editor@x.com", display_name="Bob Editor")
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    # Save with creator
    artifact = service.save_artifact(
        project_id=project.id,
        owner_user_id=creator.id,
        kind="requirements",
        name="owned.md",
        content="v1",
    )
    # Create version with editor (sets updated_by_user_id)
    service.create_version(
        project_id=project.id,
        artifact_id=artifact.id,
        created_by_user_id=editor.id,
        content="v2",
    )

    folders = service.list_artifact_tree(project_id=project.id)
    req_folder = next(f for f in folders if f["name"] == "requirements")
    entry = req_folder["entries"][0]

    assert entry["created_by_display"] == "Alice Creator"
    assert entry["updated_by_display"] == "Bob Editor"
    # PII discipline: no email in the entry
    assert "creator@x.com" not in str(entry)
    assert "editor@x.com" not in str(entry)


def test_list_artifact_tree_handles_null_creator(db_session: Session, tmp_path: Path) -> None:
    """Artifact with created_by_user_id=None returns created_by_display=None without crashing."""
    project = _create_project(db_session)
    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    service.save_artifact(
        project_id=project.id,
        owner_user_id=None,
        kind="requirements",
        name="anon.md",
        content="anon",
    )

    folders = service.list_artifact_tree(project_id=project.id)
    req_folder = next(f for f in folders if f["name"] == "requirements")
    entry = req_folder["entries"][0]

    assert entry["created_by_display"] is None
    assert entry["updated_by_display"] is None


def test_list_artifact_tree_is_cross_project_scoped(db_session: Session, tmp_path: Path) -> None:
    """Artifacts from project B never appear in project A's tree."""
    project_a = _create_project(db_session)
    project_b = Project(name="Project B")
    db_session.add(project_b)
    db_session.commit()

    service = ArtifactService(db_session, LocalArtifactStorage(tmp_path))

    service.save_artifact(
        project_id=project_a.id,
        owner_user_id=None,
        kind="requirements",
        name="a_req.md",
        content="a",
    )
    service.save_artifact(
        project_id=project_b.id,
        owner_user_id=None,
        kind="requirements",
        name="b_req.md",
        content="b",
    )

    folders_a = service.list_artifact_tree(project_id=project_a.id)
    req_folder_a = next(f for f in folders_a if f["name"] == "requirements")
    names_a = {e["name"] for e in req_folder_a["entries"]}

    assert names_a == {"a_req.md"}, "project B artifact leaked into project A's tree"

    folders_b = service.list_artifact_tree(project_id=project_b.id)
    req_folder_b = next(f for f in folders_b if f["name"] == "requirements")
    names_b = {e["name"] for e in req_folder_b["entries"]}

    assert names_b == {"b_req.md"}, "project A artifact leaked into project B's tree"


def test_storage_object_not_found_is_a_file_not_found_error() -> None:
    """Subclassing FileNotFoundError lets existing handlers map both backends to 404."""
    assert issubclass(StorageObjectNotFoundError, FileNotFoundError)


def test_local_storage_read_missing_object_raises_storage_object_not_found(tmp_path: Path) -> None:
    """A dangling key (object deleted on disk, DB row kept) raises the typed not-found error."""
    storage = LocalArtifactStorage(tmp_path)
    with pytest.raises(StorageObjectNotFoundError, match="missing.md"):
        storage.read(f"projects/{uuid4()}/requirements/{uuid4()}/v1/missing.md")


def test_s3_storage_read_missing_key_raises_storage_object_not_found() -> None:
    """A botocore NoSuchKey is mapped to the storage-agnostic not-found error."""
    storage = S3ArtifactStorage("localhost:8333", "key", "secret", "bucket")
    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )
    storage.s3 = fake_s3
    with pytest.raises(StorageObjectNotFoundError, match="gone.md"):
        storage.read("projects/x/requirements/aid/v1/gone.md")


def test_s3_storage_read_other_client_error_propagates() -> None:
    """Non-missing S3 errors (e.g. AccessDenied) must NOT be swallowed as not-found."""
    storage = S3ArtifactStorage("localhost:8333", "key", "secret", "bucket")
    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject"
    )
    storage.s3 = fake_s3
    with pytest.raises(ClientError, match="AccessDenied"):
        storage.read("projects/x/requirements/aid/v1/denied.md")


def test_s3_storage_read_404_code_maps_to_storage_object_not_found() -> None:
    """Some S3-compatible gateways report a missing object with code '404'."""
    storage = S3ArtifactStorage("localhost:8333", "key", "secret", "bucket")
    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "GetObject"
    )
    storage.s3 = fake_s3
    with pytest.raises(StorageObjectNotFoundError, match="code404.md"):
        storage.read("projects/x/requirements/aid/v1/code404.md")


def test_s3_storage_read_clienterror_without_error_code_propagates() -> None:
    """A ClientError whose response carries no error code must re-raise, not be swallowed."""
    storage = S3ArtifactStorage("localhost:8333", "key", "secret", "bucket")
    fake_s3 = MagicMock()
    fake_s3.get_object.side_effect = ClientError({}, "GetObject")
    storage.s3 = fake_s3
    with pytest.raises(ClientError, match="GetObject"):
        storage.read("projects/x/requirements/aid/v1/weird.md")
