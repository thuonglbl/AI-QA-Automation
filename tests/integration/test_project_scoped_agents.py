"""Tests for project-scoped artifact persistence in Bob, Mary, and Sarah agents."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.agents.bob import BobAgent
from ai_qa.agents.mary import MaryAgent
from ai_qa.agents.sarah import GeneratedScript, SarahAgent
from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import LocalArtifactStorage
from ai_qa.db.base import Base
from ai_qa.db.models import Artifact, ArtifactVersion, Project, User
from ai_qa.models import StageResult, TestCase, TestCaseStep
from ai_qa.pipelines.context import PipelineContext
from ai_qa.threads.models import AgentRun, Thread


@pytest.fixture
def project_context(tmp_path: Path) -> Generator[PipelineContext]:
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
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    user = User(
        email="member@example.com",
        display_name="member",
        password_hash="hash",
        role="standard",
        is_active=True,
    )
    project = Project(name="Scoped", created_by_user=user)
    session.add_all([user, project])
    session.commit()
    thread = Thread(project_id=project.id, user_id=user.id)
    session.add(thread)
    session.flush()
    run = AgentRun(thread_id=thread.id, status="running")
    session.add(run)
    session.commit()

    yield PipelineContext(
        project_id=project.id,
        user_id=user.id,
        user_email=user.email,
        artifact_service=ArtifactService(session, LocalArtifactStorage(root=tmp_path)),
        agent_run_id=run.id,
    )

    session.close()
    engine.dispose()


@pytest.mark.asyncio
async def test_bob_approve_saves_requirement_artifact(project_context: PipelineContext) -> None:
    assert project_context.artifact_service is not None
    bob = BobAgent()
    bob.set_project_context(project_context)
    bob.pages = [
        {
            "page_id": "123",
            "page_title": "Login Page",
            "source_url": "https://example.test/wiki/login",
            "requirement_md": "# Login requirement",
            "raw_html": "<h1>Login requirement</h1>",
        }
    ]

    bob.phase = "review_markdown"
    bob.current_page_index = 0
    bob.output_files_saved = 0

    await bob.handle_approve(
        {"action": "approved", "page_id": "123", "markdown": "# Login requirement"}
    )

    requirements = project_context.artifact_service.list_artifacts(
        project_id=project_context.project_id, kind="requirements"
    )
    assert len(requirements) == 1
    assert requirements[0].agent_run_id == project_context.agent_run_id
    content = project_context.artifact_service.read_current_content(requirements[0])
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    assert content == "# Login requirement"


@pytest.mark.asyncio
async def test_mary_writes_approved_test_cases_to_artifacts(
    project_context: PipelineContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert project_context.artifact_service is not None
    project_context.artifact_service.save_artifact(
        project_id=project_context.project_id,
        owner_user_id=project_context.user_id,
        agent_run_id=project_context.agent_run_id,
        kind="requirements",
        name="login.md",
        content="# Login requirement",
    )
    mary = MaryAgent()
    mary.set_project_context(project_context)
    generated = TestCase(
        title="Login succeeds",
        preconditions=["User exists"],
        steps=[TestCaseStep(number=1, action="Fill login", target="Login form")],
        expected_results=["Dashboard is shown"],
    )

    async def fake_extract_batch(
        requirements_paths: list[Path], source_urls: list[str]
    ) -> StageResult:
        assert len(requirements_paths) == 1
        assert requirements_paths[0].read_text(encoding="utf-8") == "# Login requirement"
        return StageResult(success=True, data=[generated], errors=[], warnings=[], confidence=1.0)

    monkeypatch.setattr(mary.extractor, "extract_batch", fake_extract_batch)

    result = await mary.process({})
    assert result.success
    await mary.handle_approve()

    testcases = project_context.artifact_service.list_artifacts(
        project_id=project_context.project_id, kind="testcase"
    )
    assert len(testcases) == 1
    assert testcases[0].agent_run_id == project_context.agent_run_id
    content = project_context.artifact_service.read_current_content(testcases[0])
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    assert "Login succeeds" in content


@pytest.mark.asyncio
async def test_sarah_loads_test_cases_and_saves_approved_script(
    project_context: PipelineContext,
) -> None:
    assert project_context.artifact_service is not None
    test_case = TestCase(
        title="Login succeeds",
        preconditions=["User exists"],
        steps=[TestCaseStep(number=1, action="Fill login", target="Login form")],
        expected_results=["Dashboard is shown"],
    )
    project_context.artifact_service.save_artifact(
        project_id=project_context.project_id,
        owner_user_id=project_context.user_id,
        agent_run_id=project_context.agent_run_id,
        kind="testcase",
        name="login-succeeds.json",
        content=test_case.model_dump_json(indent=2),
    )

    sarah = SarahAgent()
    sarah.set_project_context(project_context)

    loaded = await sarah._load_test_cases()
    assert loaded.success
    assert loaded.data is not None
    assert loaded.data[0].title == "Login succeeds"

    sarah._generated_scripts = [
        GeneratedScript(
            test_case=test_case,
            script_content="test('login succeeds', async ({ page }) => {});",
            file_path="login-succeeds.spec.ts",
            confidence=0.9,
        )
    ]

    await sarah.handle_approve()

    scripts = project_context.artifact_service.list_artifacts(
        project_id=project_context.project_id, kind="playwright_script"
    )
    assert len(scripts) == 1
    assert scripts[0].agent_run_id == project_context.agent_run_id
    content = project_context.artifact_service.read_current_content(scripts[0])
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    assert "login succeeds" in content
