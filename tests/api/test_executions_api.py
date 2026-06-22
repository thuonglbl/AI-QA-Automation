"""Tests for the execution review read API (Story 14.6).

Drives the real FastAPI app via the shared-SQLite ``client`` fixture; auth via
``app.dependency_overrides`` + bearer tokens (never ``mock.patch`` a dependency).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.db.models import Project, ProjectMembership, TestExecutionResult, User
from ai_qa.threads.models import AgentRun, Thread


def _seed_project(db: Session, member: User) -> Project:
    project = Project(name=f"ExecProj-{member.email}", enabled_providers=["openai"])
    db.add(project)
    db.commit()
    db.refresh(project)
    db.add(ProjectMembership(project_id=project.id, user_id=member.id, role="member"))
    db.commit()
    return project


def _seed_run(
    db: Session,
    project: Project,
    member: User,
    results: list[tuple[str, str, str]],
    *,
    created_at: datetime,
) -> AgentRun:
    thread = Thread(project_id=project.id, user_id=member.id)
    db.add(thread)
    db.flush()
    run = AgentRun(
        thread_id=thread.id,
        status="completed",
        execution_metadata={
            "started_at": created_at.isoformat(),
            "completed_at": created_at.isoformat(),
            "duration_ms": 1000,
            "browsers": sorted({b for (_t, b, _s) in results}),
            "unavailable_browsers": [],
        },
        created_at=created_at,
    )
    db.add(run)
    db.flush()
    for test_name, browser, status in results:
        db.add(
            TestExecutionResult(
                agent_run_id=run.id,
                project_id=project.id,
                thread_id=thread.id,
                test_name=test_name,
                browser=browser,
                status=status,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def _headers(token_factory: Callable[[User], str], user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_factory(user)}"}


def test_list_executions_sorted_desc_with_summary(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-member@example.com")
    project = _seed_project(db_session, member)
    base = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    _seed_run(
        db_session,
        project,
        member,
        [("test_login", "chromium", "passed"), ("test_search", "chromium", "failed")],
        created_at=base,
    )
    run2 = _seed_run(
        db_session,
        project,
        member,
        [("test_x", "firefox", "passed")],
        created_at=base + timedelta(hours=1),
    )

    resp = client.get(
        f"/api/projects/{project.id}/executions", headers=_headers(token_factory, member)
    )
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 2
    # Newest first.
    assert runs[0]["run_id"] == str(run2.id)
    first = runs[1]
    assert first["total"] == 2
    assert first["passed"] == 1
    assert first["failed"] == 1
    assert first["success_rate"] == 50.0
    assert first["browsers"] == ["chromium"]


def test_list_executions_filters(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-filter@example.com")
    project = _seed_project(db_session, member)
    base = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    run = _seed_run(
        db_session,
        project,
        member,
        [("test_login", "chromium", "passed"), ("test_search", "chromium", "failed")],
        created_at=base,
    )
    headers = _headers(token_factory, member)
    url = f"/api/projects/{project.id}/executions"

    # browser filter — chromium present → run appears; firefox absent → empty.
    assert len(client.get(url, params={"browser": "chromium"}, headers=headers).json()) == 1
    assert len(client.get(url, params={"browser": "firefox"}, headers=headers).json()) == 0
    # result filter — has a failed → appears; no skipped → empty.
    assert len(client.get(url, params={"result": "failed"}, headers=headers).json()) == 1
    assert len(client.get(url, params={"result": "skipped"}, headers=headers).json()) == 0
    # thread filter.
    assert (
        len(client.get(url, params={"thread_id": str(run.thread_id)}, headers=headers).json()) == 1
    )
    assert (
        len(
            client.get(
                url,
                params={"thread_id": "00000000-0000-0000-0000-000000000001"},
                headers=headers,
            ).json()
        )
        == 0
    )
    # date filter — before the run → empty; after → appears.
    assert len(client.get(url, params={"date_from": "2026-06-22"}, headers=headers).json()) == 0
    assert len(client.get(url, params={"date_to": "2026-06-22"}, headers=headers).json()) == 1


def test_execution_detail_returns_results(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-detail@example.com")
    project = _seed_project(db_session, member)
    run = _seed_run(
        db_session,
        project,
        member,
        [("test_login", "chromium", "passed"), ("test_search", "firefox", "failed")],
        created_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
    )
    resp = client.get(
        f"/api/projects/{project.id}/executions/{run.id}",
        headers=_headers(token_factory, member),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["total"] == 2
    assert len(body["results"]) == 2
    assert {r["browser"] for r in body["results"]} == {"chromium", "firefox"}
    assert isinstance(body["attachments"], dict)


def test_parse_date_normalizes_to_utc_aware() -> None:
    """A date-only filter value must be tz-aware so it never trips a naive-vs-aware TypeError
    against the tz-aware created_at column on PostgreSQL (SQLite masks this in the suite)."""
    from ai_qa.api.executions import _parse_date

    parsed = _parse_date("2026-06-22")
    assert parsed is not None
    assert parsed.tzinfo is not None


def test_date_filter_bounds_are_inclusive_of_the_selected_day(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-sameday@example.com")
    project = _seed_project(db_session, member)
    run = _seed_run(
        db_session,
        project,
        member,
        [("test_login", "chromium", "passed")],
        created_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
    )
    assert run is not None
    headers = _headers(token_factory, member)
    url = f"/api/projects/{project.id}/executions"
    # date_to equal to the run's own calendar day must INCLUDE it (was an off-by-one before).
    assert len(client.get(url, params={"date_to": "2026-06-21"}, headers=headers).json()) == 1
    # date_from equal to the run's own day must also include it.
    assert len(client.get(url, params={"date_from": "2026-06-21"}, headers=headers).json()) == 1


def test_execution_detail_round_trips_role(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-role@example.com")
    project = _seed_project(db_session, member)
    run = _seed_run(
        db_session,
        project,
        member,
        [("test_login", "chromium", "passed")],
        created_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
    )
    row = (
        db_session.execute(
            select(TestExecutionResult).where(TestExecutionResult.agent_run_id == run.id)
        )
        .scalars()
        .first()
    )
    assert row is not None
    row.role = "Admin"
    db_session.commit()

    resp = client.get(
        f"/api/projects/{project.id}/executions/{run.id}",
        headers=_headers(token_factory, member),
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["role"] == "Admin"


def test_execution_detail_missing_run_404(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-missing@example.com")
    project = _seed_project(db_session, member)
    resp = client.get(
        f"/api/projects/{project.id}/executions/00000000-0000-0000-0000-000000000009",
        headers=_headers(token_factory, member),
    )
    assert resp.status_code == 404


def test_executions_membership_gated(
    client: TestClient,
    db_session: Session,
    user_factory: Callable[..., User],
    token_factory: Callable[[User], str],
) -> None:
    member = user_factory("exec-owner@example.com")
    non_member = user_factory("exec-outsider@example.com")
    project = _seed_project(db_session, member)
    _seed_run(
        db_session,
        project,
        member,
        [("test_login", "chromium", "passed")],
        created_at=datetime(2026, 6, 21, 9, 0, tzinfo=UTC),
    )

    # Member can list; a non-member is denied (404, no leak).
    assert (
        client.get(
            f"/api/projects/{project.id}/executions", headers=_headers(token_factory, member)
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/projects/{project.id}/executions",
            headers=_headers(token_factory, non_member),
        ).status_code
        == 404
    )
