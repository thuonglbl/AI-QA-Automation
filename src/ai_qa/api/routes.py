"""REST API endpoints for pipeline control.

These endpoints allow the frontend to:
- Start a pipeline step
- Approve agent output and continue
- Reject with feedback for correction
- Continue to next step after approval

Agent dispatch:
    A module-level registry ``_active_agents`` maps step numbers (1–5) to
    registered :class:`~ai_qa.agents.base.BaseAgent` instances. When a
    concrete agent is registered (Story 2.3 onwards) the endpoints delegate
    to it; when none is registered the stubs return the same fixed responses
    as before, keeping the frontend working during development.

Per-User Workspace:
    All endpoints now require user authentication and pass user context to agents
    for per-user workspace isolation. Files are saved to workspace/users/{email_hash}/
    instead of shared workspace directories.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.api.artifacts import get_artifact_storage
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import NOT_AUTHENTICATED_DETAIL
from ai_qa.api.projects import RESOURCE_NOT_FOUND_DETAIL, require_project_member_or_admin
from ai_qa.api.schemas import (
    ActionResponse,
    ApproveRequest,
    ContinueRequest,
    ConversationData,
    ConversationSaveRequest,
    NavigateRequest,
    RejectRequest,
    SkipRequest,
    StartRequest,
)
from ai_qa.artifacts.service import ArtifactService
from ai_qa.artifacts.storage import ArtifactStorage
from ai_qa.config import AppSettings
from ai_qa.db.health import check_database_health
from ai_qa.db.models import Project, User
from ai_qa.pipelines.context import PipelineContext
from ai_qa.pipelines.run_service import PipelineRunService

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Active agent registry
# ---------------------------------------------------------------------------
# Maps pipeline step number (1–5) to a registered BaseAgent instance.
# Concrete agents are registered by their respective stories (2.3, 2.8, 3.5, …).
# Story 2.3 establishes this infrastructure and the first concrete agents.
# NOTE: In production with auth, agents are per-user instances.
_active_agents: dict[int, BaseAgent] = {}

# Per-user agent instances: {user_email: {step: BaseAgent}}
_user_agents: dict[str, dict[int, BaseAgent]] = {}

# Project-mode agent instances: {(user_id, project_id, step): BaseAgent}
_project_user_agents: dict[tuple[str, str, int], BaseAgent] = {}

DbSessionDependency = Depends(get_db_session_dependency)
ArtifactStorageDependency = Depends(get_artifact_storage)


def _clone_agent_for_workspace(step: int, user_email: str | None) -> BaseAgent | None:
    template = _active_agents.get(step)
    if template is None:
        return None

    agent_class = template.__class__
    if user_email:
        user_agent = agent_class()  # type: ignore[call-arg]
        user_agent.set_user_context(user_email)
        return user_agent
    return template


def _get_agent_for_user(step: int, user_email: str | None) -> BaseAgent | None:
    """Get or create compatibility-mode agent instance for a specific user."""
    if user_email:
        if user_email not in _user_agents:
            _user_agents[user_email] = {}
        if step not in _user_agents[user_email]:
            user_agent = _clone_agent_for_workspace(step, user_email)
            if user_agent is None:
                return None
            _user_agents[user_email][step] = user_agent
            logger.info("Created per-user agent for step %d, user %s", step, user_email)
        return _user_agents[user_email][step]
    return _active_agents.get(step)


def _get_agent_for_project(step: int, context: PipelineContext) -> BaseAgent | None:
    """Get or create an agent keyed by user, project, and step for project mode."""
    key = (str(context.user_id), str(context.project_id), step)
    if key not in _project_user_agents:
        user_agent = _clone_agent_for_workspace(step, context.user_email)
        if user_agent is None:
            return None
        _project_user_agents[key] = user_agent
        logger.info(
            "Created project agent for step %d, user %s, project %s",
            step,
            context.user_email,
            context.project_id,
        )
    agent = _project_user_agents[key]
    if context.pipeline_run_id is None and agent.project_context is not None:
        context.pipeline_run_id = agent.project_context.pipeline_run_id
    agent.set_project_context(context)
    return agent


def _mark_context_run_failed(
    context: PipelineContext | None,
    db: Session,
    *,
    step: int,
    action: str,
    error: Exception | str,
) -> None:
    """Mark a project-scoped pipeline run failed when an agent action errors."""
    if context is None or context.pipeline_run_id is None:
        return
    PipelineRunService(db).mark_failed(
        context.pipeline_run_id,
        {
            "failed_step": step,
            "failed_action": action,
            "error": str(error),
        },
    )


def _mark_context_run_finished_for_agent(
    context: PipelineContext | None,
    db: Session,
    agent: BaseAgent,
    *,
    step: int,
    action: str,
) -> None:
    """Finalize a project-scoped run when the agent reaches a terminal state."""
    if context is None or context.pipeline_run_id is None:
        return
    if agent.state == AgentState.ERROR:
        PipelineRunService(db).mark_failed(
            context.pipeline_run_id,
            {
                "failed_step": step,
                "failed_action": action,
                "agent": agent.name,
            },
        )
        return
    if agent.state not in (AgentState.DONE, AgentState.COMPLETED):
        return
    PipelineRunService(db).mark_completed(
        context.pipeline_run_id,
        {
            "completed_step": step,
            "completed_action": action,
            "agent": agent.name,
        },
    )


def _project_status_for_agent(agent: BaseAgent) -> str:
    if agent.state == AgentState.COMPLETED:
        return "completed"
    if agent.state == AgentState.DONE:
        return "done"
    return str(agent.state)


def _request_project_id(request: BaseModel) -> UUID | None:
    return getattr(request, "project_id", None)


async def _build_pipeline_context(
    *,
    project_id: UUID | None,
    http_request: Request,
    db: Session,
    storage: ArtifactStorage,
    create_run: bool = False,
) -> PipelineContext | None:
    """Validate request auth/project access and build project-scoped context."""
    session_user = getattr(http_request.state, "user", None)
    if session_user is None:
        if project_id is None:
            return None
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)
    if project_id is None:
        if getattr(session_user, "user_id", None) is None:
            return None
        raise HTTPException(status_code=422, detail="project_id is required")

    try:
        user_id = UUID(str(session_user.user_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL) from exc

    current_user = db.get(User, user_id)
    if current_user is None or not current_user.is_active:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED_DETAIL)

    project = await require_project_member_or_admin(project_id, current_user, db)
    if project.id != project_id:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL)

    pipeline_run_id = None
    if create_run:
        pipeline_run = PipelineRunService(db).start_run(
            project_id=project.id,
            started_by_user_id=current_user.id,
        )
        pipeline_run_id = pipeline_run.id

    return PipelineContext(
        project_id=project.id,
        user_id=current_user.id,
        user_email=current_user.email,
        artifact_service=ArtifactService(db, storage),
        pipeline_run_id=pipeline_run_id,
    )


def _agent_for_context(
    step: int, context: PipelineContext | None, user_email: str | None
) -> BaseAgent | None:
    if context is not None:
        return _get_agent_for_project(step, context)
    return _get_agent_for_user(step, user_email)


def register_agent(agent: BaseAgent) -> None:
    """Register a concrete agent instance for its pipeline step.

    Called during application startup by agent-specific stories.

    Args:
        agent: Fully initialised :class:`~ai_qa.agents.base.BaseAgent` subclass.

    Raises:
        ValueError: If agent.step_number is not in valid range (1-5).
    """
    if not 1 <= agent.step_number <= 5:
        raise ValueError(f"Invalid step_number: {agent.step_number}. Must be 1-5.")
    if agent.step_number in _active_agents:
        logger.warning(
            "Overwriting existing agent for step %d (old: %s, new: %s)",
            agent.step_number,
            _active_agents[agent.step_number].name,
            agent.name,
        )
    logger.info("Registering agent %s for step %d", agent.name, agent.step_number)
    _active_agents[agent.step_number] = agent


def get_active_agent(step: int) -> BaseAgent | None:
    """Return the registered agent for *step*, or ``None`` if not yet registered.

    Args:
        step: Pipeline step number (1-5).

    Returns:
        The registered BaseAgent instance, or None if no agent is registered.
    """
    return _active_agents.get(step)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/start", response_model=ActionResponse)
async def start_step(
    request: StartRequest,
    http_request: Request,
    db: Session = DbSessionDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
) -> ActionResponse:
    """Start a pipeline step.

    Triggers the specified agent to begin processing.
    Returns immediately; use WebSocket for real-time updates.
    """
    # Get user context from auth middleware
    user = getattr(http_request.state, "user", None)
    user_email = user.email if user else None
    context = await _build_pipeline_context(
        project_id=request.project_id,
        http_request=http_request,
        db=db,
        storage=storage,
        create_run=True,
    )

    agent = _agent_for_context(request.step, context, user_email)
    if agent is not None:
        try:
            input_dict = (
                dict(request.input_data)
                if not isinstance(request.input_data, dict)
                else request.input_data
            )
            await agent.handle_start(input_dict)
        except Exception as e:
            logger.error("Agent start failed for step %d: %s", request.step, e)
            _mark_context_run_failed(context, db, step=request.step, action="start", error=e)
            raise
        _mark_context_run_finished_for_agent(context, db, agent, step=request.step, action="start")
        return ActionResponse(
            success=True,
            message=f"Step {request.step} started",
            current_step=request.step,
            status=_project_status_for_agent(agent),
        )

    # Stub behaviour: no concrete agent registered for this step yet
    logger.debug("No agent registered for step %d — returning stub response", request.step)
    return ActionResponse(
        success=True,
        message=f"Step {request.step} started",
        current_step=request.step,
        status="processing",
    )


@router.post("/approve", response_model=ActionResponse)
async def approve_step(
    request: ApproveRequest,
    http_request: Request,
    db: Session = DbSessionDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
) -> ActionResponse:
    """Approve agent output and continue.

    User approves the current output and wants to proceed.
    """
    user = getattr(http_request.state, "user", None)
    user_email = user.email if user else None
    context = await _build_pipeline_context(
        project_id=_request_project_id(request),
        http_request=http_request,
        db=db,
        storage=storage,
    )

    agent = _agent_for_context(request.step, context, user_email)
    if agent is not None:
        try:
            await agent.handle_approve()
        except Exception as e:
            logger.error("Agent approve failed for step %d: %s", request.step, e)
            _mark_context_run_failed(context, db, step=request.step, action="approve", error=e)
            raise
        _mark_context_run_finished_for_agent(
            context, db, agent, step=request.step, action="approve"
        )
        return ActionResponse(
            success=True,
            message=f"Step {request.step} approved",
            current_step=request.step,
            status=_project_status_for_agent(agent),
        )

    return ActionResponse(
        success=True,
        message=f"Step {request.step} approved",
        current_step=request.step,
        status="done",
    )


@router.post("/reject", response_model=ActionResponse)
async def reject_step(
    request: RejectRequest,
    http_request: Request,
    db: Session = DbSessionDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
) -> ActionResponse:
    """Reject agent output with feedback.

    User rejects the output and provides feedback for correction.
    Agent will re-process with the feedback context.
    """
    user = getattr(http_request.state, "user", None)
    user_email = user.email if user else None
    context = await _build_pipeline_context(
        project_id=_request_project_id(request),
        http_request=http_request,
        db=db,
        storage=storage,
    )

    agent = _agent_for_context(request.step, context, user_email)
    if agent is not None:
        try:
            await agent.handle_reject(request.feedback)
        except Exception as e:
            logger.error("Agent reject failed for step %d: %s", request.step, e)
            _mark_context_run_failed(context, db, step=request.step, action="reject", error=e)
            raise
        return ActionResponse(
            success=True,
            message=f"Step {request.step} rejected with feedback",
            current_step=request.step,
            status=_project_status_for_agent(agent),
        )

    return ActionResponse(
        success=True,
        message=f"Step {request.step} rejected with feedback",
        current_step=request.step,
        status="processing",  # Returns to processing for correction
    )


@router.post("/continue", response_model=ActionResponse)
async def continue_pipeline(
    request: ContinueRequest,
    http_request: Request,
    db: Session = DbSessionDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
) -> ActionResponse:
    """Continue to next step after approval.

    User clicks Continue after a step is marked Done.
    Advances to the next step or completes if step 5.
    """
    # Validate project context when authenticated project mode is used.
    await _build_pipeline_context(
        project_id=_request_project_id(request),
        http_request=http_request,
        db=db,
        storage=storage,
    )
    next_step = request.from_step + 1
    if next_step > 5:
        return ActionResponse(
            success=True,
            message="Pipeline completed",
            current_step=5,
            status="completed",
        )
    return ActionResponse(
        success=True,
        message=f"Continuing to step {next_step}",
        current_step=next_step,
        status="start",
    )


@router.post("/skip", response_model=ActionResponse)
async def skip_item(
    request: SkipRequest,
    http_request: Request,
    db: Session = DbSessionDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
) -> ActionResponse:
    """Skip current item during review.

    Used by Sarah agent to skip current script review
    (hand off to automation engineer for manual review).
    """
    user = getattr(http_request.state, "user", None)
    user_email = user.email if user else None
    context = await _build_pipeline_context(
        project_id=_request_project_id(request),
        http_request=http_request,
        db=db,
        storage=storage,
    )

    agent = _agent_for_context(request.step, context, user_email)
    if agent is not None and hasattr(agent, "handle_skip"):
        try:
            await agent.handle_skip()
        except Exception as e:
            logger.error("Agent skip failed for step %d: %s", request.step, e)
            _mark_context_run_failed(context, db, step=request.step, action="skip", error=e)
            raise
        _mark_context_run_finished_for_agent(context, db, agent, step=request.step, action="skip")
        return ActionResponse(
            success=True,
            message=f"Step {request.step} item skipped",
            current_step=request.step,
            status="review_request",
        )

    return ActionResponse(
        success=True,
        message=f"Step {request.step} item skipped (stub)",
        current_step=request.step,
        status="review_request",
    )


@router.post("/navigate", response_model=ActionResponse)
async def navigate_review(
    request: NavigateRequest,
    http_request: Request,
    db: Session = DbSessionDependency,
    storage: ArtifactStorage = ArtifactStorageDependency,
) -> ActionResponse:
    """Navigate between items during review (Next/Previous).

    Used for paginated review where user navigates between
    test cases or scripts.
    """
    user = getattr(http_request.state, "user", None)
    user_email = user.email if user else None
    context = await _build_pipeline_context(
        project_id=_request_project_id(request),
        http_request=http_request,
        db=db,
        storage=storage,
    )

    agent = _agent_for_context(request.step, context, user_email)
    if agent is not None and hasattr(agent, "handle_navigate"):
        try:
            await agent.handle_navigate(request.direction)
        except Exception as e:
            logger.error("Agent navigate failed for step %d: %s", request.step, e)
            _mark_context_run_failed(context, db, step=request.step, action="navigate", error=e)
            raise
        return ActionResponse(
            success=True,
            message=f"Navigated {request.direction}",
            current_step=request.step,
            status="review_request",
        )

    return ActionResponse(
        success=True,
        message=f"Navigated {request.direction} (stub)",
        current_step=request.step,
        status="review_request",
    )


@router.get("/health")
async def health_check(http_request: Request) -> dict[str, object]:
    """Health check endpoint including database readiness."""
    settings = getattr(http_request.app.state, "settings", AppSettings())
    database = check_database_health(settings)
    status = "healthy" if database.status in {"healthy", "not_configured"} else "degraded"
    return {"status": status, "version": "0.1.0", "database": database.as_dict()}


@router.get("/projects/{project_id}/conversation", response_model=ConversationData)
async def get_conversation(
    project_id: UUID,
    project: Project = Depends(require_project_member_or_admin),  # noqa: B008
) -> ConversationData:
    """Get project's saved conversation history from database.

    Loads conversation from Project.conversation_data.
    Returns empty conversation if null.
    """

    if not project.conversation_data:
        return ConversationData()

    try:
        return ConversationData.model_validate(project.conversation_data)
    except Exception as e:
        logger.error("Failed to load conversation for project %s: %s", project_id, e)
        return ConversationData()


@router.post("/projects/{project_id}/conversation", response_model=ActionResponse)
async def save_conversation(
    project_id: UUID,
    request: ConversationSaveRequest,
    project: Project = Depends(require_project_member_or_admin),  # noqa: B008
    db: Session = DbSessionDependency,
) -> ActionResponse:
    """Save project's conversation history to database.

    Saves to Project.conversation_data, updates status and current_step.
    """

    try:
        project.conversation_data = request.conversation.model_dump(mode="json")
        project.current_step = request.conversation.current_step
        project.status = request.conversation.status
        db.commit()
        return ActionResponse(
            success=True,
            message="Conversation saved",
            current_step=request.conversation.current_step,
            status=request.conversation.status,
        )
    except Exception as e:
        db.rollback()
        logger.error("Failed to save conversation for project %s: %s", project_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to save conversation: {e}") from e
