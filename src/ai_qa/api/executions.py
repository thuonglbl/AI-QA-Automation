"""Execution review read API (Story 14.6, project-scoped + membership-gated).

Serves the execution **history** (list of runs, sorted by run time, filterable by
thread/browser/result/date) and a single run's **detail** (per-``(test, browser)`` results +
attachment link map) — the data the Jack step-5 review UX renders. Reads
``TestExecutionResult`` rows + ``AgentRun`` (the execution run); attachment ids come from the
run's ``report.json`` companion (Story 14.5). Returns only scrubbed fields — no secret ever
transits this surface.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.db.models import Artifact, TestExecutionResult, User
from ai_qa.threads.models import AgentRun

logger = logging.getLogger(__name__)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

router = APIRouter(prefix="/projects", tags=["executions"])


class ExecutionResultResponse(BaseModel):
    test_name: str
    browser: str
    role: str | None = None
    status: str
    duration_ms: int | None = None
    failure_classification: str | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    source_script_artifact_id: UUID | None = None
    source_test_case_artifact_id: UUID | None = None


class ExecutionRunSummaryResponse(BaseModel):
    run_id: UUID
    thread_id: UUID | None = None
    created_at: datetime
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    success_rate: float
    browsers: list[str]
    unavailable_browsers: list[dict[str, str]]
    report_artifact_id: UUID | None = None


class ExecutionDetailResponse(BaseModel):
    summary: ExecutionRunSummaryResponse
    results: list[ExecutionResultResponse]
    attachments: dict[str, Any]


async def _project_for_member(project_id: UUID, current_user: User, db: Session) -> Any:
    from ai_qa.api.projects import require_project_member_or_admin

    return await require_project_member_or_admin(project_id, current_user, db)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Date-only inputs (the FE <input type="date">) parse naive; normalize to UTC so
    # comparisons against the tz-aware created_at column never raise on PostgreSQL.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _report_artifact_id(db: Session, project_id: UUID, run_id: UUID) -> UUID | None:
    """The run's visible report.md artifact id, if persisted (Story 14.5)."""
    rows = (
        db.execute(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.agent_run_id == run_id,
                Artifact.kind == "report",
            )
        )
        .scalars()
        .all()
    )
    return rows[0].id if rows else None


def _report_artifact_ids(db: Session, project_id: UUID, run_ids: list[UUID]) -> dict[UUID, UUID]:
    """Batched {run_id: report.md artifact id} for the given runs (Story 14.5), one query."""
    if not run_ids:
        return {}
    rows = (
        db.execute(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.agent_run_id.in_(run_ids),
                Artifact.kind == "report",
            )
        )
        .scalars()
        .all()
    )
    out: dict[UUID, UUID] = {}
    for artifact in rows:
        if artifact.agent_run_id is not None and artifact.agent_run_id not in out:
            out[artifact.agent_run_id] = artifact.id
    return out


def _summary_for_run(
    run: AgentRun | None,
    run_id: UUID,
    rows: list[TestExecutionResult],
    report_artifact_id: UUID | None,
) -> ExecutionRunSummaryResponse:
    meta: dict[str, Any] = (run.execution_metadata or {}) if run is not None else {}
    total = len(rows)
    passed = sum(1 for r in rows if r.status == "passed")
    failed = sum(1 for r in rows if r.status == "failed")
    errors = sum(1 for r in rows if r.status == "error")
    skipped = sum(1 for r in rows if r.status == "skipped")
    browsers = sorted({r.browser for r in rows})
    created = run.created_at if run is not None else datetime.now(UTC)
    return ExecutionRunSummaryResponse(
        run_id=run_id,
        thread_id=run.thread_id if run is not None else None,
        created_at=created,
        started_at=meta.get("started_at"),
        completed_at=meta.get("completed_at"),
        duration_ms=meta.get("duration_ms"),
        total=total,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        success_rate=round((passed / total) * 100, 1) if total else 0.0,
        browsers=browsers or list(meta.get("browsers") or []),
        unavailable_browsers=list(meta.get("unavailable_browsers") or []),
        report_artifact_id=report_artifact_id,
    )


@router.get("/{project_id}/executions", response_model=list[ExecutionRunSummaryResponse])
async def list_executions(
    project_id: UUID,
    thread_id: UUID | None = None,
    browser: str | None = None,
    result: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> list[ExecutionRunSummaryResponse]:
    """List execution runs for the project, newest first, with optional filters (AC3)."""
    await _project_for_member(project_id, current_user, db)

    all_rows = (
        db.execute(select(TestExecutionResult).where(TestExecutionResult.project_id == project_id))
        .scalars()
        .all()
    )

    by_run: dict[UUID, list[TestExecutionResult]] = {}
    for row in all_rows:
        by_run.setdefault(row.agent_run_id, []).append(row)

    # Batch-load runs + report-artifact ids once instead of ~2 queries per run (N+1).
    run_ids = list(by_run.keys())
    runs_by_id: dict[UUID, AgentRun] = (
        {r.id: r for r in db.execute(select(AgentRun).where(AgentRun.id.in_(run_ids))).scalars()}
        if run_ids
        else {}
    )
    report_ids_by_run = _report_artifact_ids(db, project_id, run_ids)

    dfrom = _parse_date(date_from)
    dto = _parse_date(date_to)

    summaries: list[ExecutionRunSummaryResponse] = []
    for run_id, rows in by_run.items():
        # Row-level filters select WHICH runs appear; counts stay the run's full totals.
        if browser is not None and not any(r.browser == browser for r in rows):
            continue
        if result is not None and not any(r.status == result for r in rows):
            continue
        summary = _summary_for_run(
            runs_by_id.get(run_id), run_id, rows, report_ids_by_run.get(run_id)
        )
        if thread_id is not None and summary.thread_id != thread_id:
            continue
        # Compare by calendar day so the date_from/date_to bounds are inclusive of the
        # selected days and the comparison never trips a naive-vs-aware TypeError.
        if dfrom is not None and summary.created_at.date() < dfrom.date():
            continue
        if dto is not None and summary.created_at.date() > dto.date():
            continue
        summaries.append(summary)

    summaries.sort(key=lambda s: s.created_at, reverse=True)
    return summaries


@router.get("/{project_id}/executions/{run_id}", response_model=ExecutionDetailResponse)
async def get_execution_detail(
    project_id: UUID,
    run_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> ExecutionDetailResponse:
    """One run's detail: summary + per-(test, browser) results + attachment link map (AC2)."""
    await _project_for_member(project_id, current_user, db)

    rows = (
        db.execute(
            select(TestExecutionResult).where(
                TestExecutionResult.project_id == project_id,
                TestExecutionResult.agent_run_id == run_id,
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Execution run not found")

    run = db.get(AgentRun, run_id)
    report_artifact_id = _report_artifact_id(db, project_id, run_id)
    summary = _summary_for_run(run, run_id, list(rows), report_artifact_id)
    results = [
        ExecutionResultResponse(
            test_name=r.test_name,
            browser=r.browser,
            role=r.role,
            status=r.status,
            duration_ms=r.duration_ms,
            failure_classification=r.failure_classification,
            error_message=r.error_message,
            stack_trace=r.stack_trace,
            source_script_artifact_id=r.source_script_artifact_id,
            source_test_case_artifact_id=r.source_test_case_artifact_id,
        )
        for r in rows
    ]
    attachments = _load_attachment_map(db, project_id, run_id)
    return ExecutionDetailResponse(summary=summary, results=results, attachments=attachments)


def _load_attachment_map(db: Session, project_id: UUID, run_id: UUID) -> dict[str, Any]:
    """Best-effort attachment link map from the run's report.json (Story 14.5). {} on miss."""
    from ai_qa.api.artifacts import get_artifact_storage
    from ai_qa.artifacts.service import ArtifactService

    rows = (
        db.execute(
            select(Artifact).where(
                Artifact.project_id == project_id,
                Artifact.agent_run_id == run_id,
                Artifact.kind == "configuration",
            )
        )
        .scalars()
        .all()
    )
    report_json = next((a for a in rows if a.name.endswith("report.json")), None)
    if report_json is None:
        return {}
    try:
        service = ArtifactService(db, get_artifact_storage())
        content = service.read_current_content(report_json).decode("utf-8")
        parsed = json.loads(content)
        attachments = parsed.get("attachments") if isinstance(parsed, dict) else None
        return attachments if isinstance(attachments, dict) else {}
    except Exception as exc:  # noqa: BLE001 — attachments are best-effort
        logger.debug("Could not load attachment map for run %s: %s", run_id, exc)
        return {}
