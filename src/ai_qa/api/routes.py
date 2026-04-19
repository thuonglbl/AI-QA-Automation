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
"""

import logging

from fastapi import APIRouter

from ai_qa.agents.base import BaseAgent
from ai_qa.api.schemas import (
    ActionResponse,
    ApproveRequest,
    ContinueRequest,
    RejectRequest,
    StartRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Active agent registry
# ---------------------------------------------------------------------------
# Maps pipeline step number (1–5) to a registered BaseAgent instance.
# Concrete agents are registered by their respective stories (2.3, 2.8, 3.5, …).
# Story 2.3 establishes this infrastructure and the first concrete agents.
_active_agents: dict[int, BaseAgent] = {}


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
async def start_step(request: StartRequest) -> ActionResponse:
    """Start a pipeline step.

    Triggers the specified agent to begin processing.
    Returns immediately; use WebSocket for real-time updates.
    """
    agent = _active_agents.get(request.step)
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
            raise
        return ActionResponse(
            success=True,
            message=f"Step {request.step} started",
            current_step=request.step,
            status="processing",
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
async def approve_step(request: ApproveRequest) -> ActionResponse:
    """Approve agent output and continue.

    User approves the current output and wants to proceed.
    """
    agent = _active_agents.get(request.step)
    if agent is not None:
        try:
            await agent.handle_approve()
        except Exception as e:
            logger.error("Agent approve failed for step %d: %s", request.step, e)
            raise
        return ActionResponse(
            success=True,
            message=f"Step {request.step} approved",
            current_step=request.step,
            status="done",
        )

    return ActionResponse(
        success=True,
        message=f"Step {request.step} approved",
        current_step=request.step,
        status="done",
    )


@router.post("/reject", response_model=ActionResponse)
async def reject_step(request: RejectRequest) -> ActionResponse:
    """Reject agent output with feedback.

    User rejects the output and provides feedback for correction.
    Agent will re-process with the feedback context.
    """
    agent = _active_agents.get(request.step)
    if agent is not None:
        try:
            await agent.handle_reject(request.feedback)
        except Exception as e:
            logger.error("Agent reject failed for step %d: %s", request.step, e)
            raise
        return ActionResponse(
            success=True,
            message=f"Step {request.step} rejected with feedback",
            current_step=request.step,
            status="processing",
        )

    return ActionResponse(
        success=True,
        message=f"Step {request.step} rejected with feedback",
        current_step=request.step,
        status="processing",  # Returns to processing for correction
    )


@router.post("/continue", response_model=ActionResponse)
async def continue_pipeline(request: ContinueRequest) -> ActionResponse:
    """Continue to next step after approval.

    User clicks Continue after a step is marked Done.
    Advances to the next step or completes if step 5.
    """
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


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}
