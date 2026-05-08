"""BaseAgent abstract class implementing the shared agent lifecycle.

All pipeline agents (Alice, Bob, Mary, Sarah, Jack) must subclass BaseAgent.

Lifecycle pattern:
    START → PROCESSING → REVIEW_REQUEST → DONE
                ↑__________________________|  (Reject loops back)

Usage:
    class AliceAgent(BaseAgent):
        async def process(self, input_data, feedback=None):
            # implement agent-specific logic
            return StageResult(success=True, data={...})
"""

# Standard library
import json
import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any

# Local
from ai_qa.exceptions import PipelineError
from ai_qa.models import AgentMessage, StageResult
from ai_qa.pipelines.context import PipelineContext

logger = logging.getLogger(__name__)

# Workspace root — relative to CWD (project root when using `uv run`)
WORKSPACE_DIR = Path("workspace")

# Per-user workspace subdirectory names
USER_WORKSPACE_SUBFOLDERS = [
    "configuration",
    "requirements",
    "testcases",
    "testscripts",
    "report",
    "audit",
]

# Legacy shared workspace subdirectory names (for backward compatibility)
WORKSPACE_SUBFOLDERS = [
    "configuration",
    "requirements",
    "testcases",
    "testscripts",
    "report",
    "audit",
]


class AgentState(StrEnum):
    """Agent lifecycle states.

    String values MUST match the TypeScript ``AgentStatus`` union type in
    ``frontend/src/types/pipeline.ts`` exactly (case-sensitive, underscore-separated).
    """

    START = "start"
    PROCESSING = "processing"
    REVIEW_REQUEST = "review_request"
    DONE = "done"
    COMPLETED = "completed"  # Step 5 (Jack) only — final state for the whole pipeline
    ERROR = "error"  # Internal error state — not exposed to TypeScript


class BaseAgent(ABC):
    """Abstract base class for all named AI pipeline agents.

    Subclasses must implement :meth:`process`.  The lifecycle methods
    ``handle_start``, ``handle_approve``, and ``handle_reject`` are
    concrete and must not be overridden unless absolutely necessary.

    Args:
        name: Agent display name ("Alice", "Bob", "Mary", "Sarah", "Jack").
        color: HEX colour string matching the frontend ``AGENTS`` constant.
        step_number: Pipeline step index (1–5).
        step_title: Human-readable label shown in the UI.
        workspace_dir: Override the workspace root path (used in tests via tmp_path).
    """

    def __init__(
        self,
        name: str,
        color: str,
        step_number: int,
        step_title: str,
        workspace_dir: Path | None = None,
        user_email: str | None = None,
    ) -> None:
        self.name = name
        self.color = color
        self.step_number = step_number
        self.step_title = step_title
        self.state: AgentState = AgentState.START
        self._agent_config: dict[str, Any] = {}
        self._user_email: str | None = user_email
        self.project_context: PipelineContext | None = None

        # Use per-user workspace if user_email is provided, otherwise legacy shared workspace
        if workspace_dir is not None:
            self._workspace_dir: Path = workspace_dir
        elif user_email is not None:
            from ai_qa.config import get_user_workspace_dir

            self._workspace_dir = get_user_workspace_dir(user_email)
        else:
            self._workspace_dir = WORKSPACE_DIR

        self._load_agent_config()
        self._create_workspace()

    # ------------------------------------------------------------------
    # Workspace helpers
    # ------------------------------------------------------------------

    def _create_workspace(self) -> None:
        """Create the workspace directory tree if not already present.

        Safe to call repeatedly — uses ``exist_ok=True``.
        """
        folders = USER_WORKSPACE_SUBFOLDERS if self._user_email else WORKSPACE_SUBFOLDERS
        for folder in folders:
            (self._workspace_dir / folder).mkdir(parents=True, exist_ok=True)
        logger.info("Workspace directories ensured at %s", self._workspace_dir.resolve())

    def set_user_context(self, user_email: str | None) -> None:
        """Set or update the user context for per-user workspace isolation.

        This method allows switching from shared workspace to per-user workspace
        when a user authenticates. Called by API routes when user context is available.

        Args:
            user_email: User's email address for per-user workspace, or None for shared workspace.
        """
        if user_email == self._user_email:
            return  # No change needed

        self._user_email = user_email

        if user_email is not None:
            from ai_qa.config import get_user_workspace_dir

            self._workspace_dir = get_user_workspace_dir(user_email)
            logger.info("Agent %s switched to per-user workspace for %s", self.name, user_email)
        # else: keep existing workspace_dir (shared mode)

        # Recreate workspace for new user
        self._create_workspace()
        self._load_agent_config()

    def set_project_context(self, context: PipelineContext | None) -> None:
        """Attach authorized project context for project-scoped execution."""
        self.project_context = context
        if context is not None:
            self._user_email = context.user_email

    # ------------------------------------------------------------------
    # Agent configuration
    # ------------------------------------------------------------------

    def _load_agent_config(self) -> None:
        """Load per-agent config from ``workspace/configuration/agents.json``.

        If the file is absent or malformed the agent silently uses empty defaults.
        Keys in ``agents.json`` are agent names in **lowercase**.
        """
        agents_json = self._workspace_dir / "configuration" / "agents.json"
        if agents_json.exists():
            try:
                with agents_json.open() as fh:
                    all_config: dict[str, Any] = json.load(fh)
                self._agent_config = all_config.get(self.name.lower(), {})
                logger.info("Loaded agent config for %s from agents.json", self.name)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load agents.json: %s — using defaults", exc)

    # ------------------------------------------------------------------
    # Messaging
    # ------------------------------------------------------------------

    async def send_message(
        self,
        content: str,
        message_type: str = "text",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Broadcast a message to all connected WebSocket clients.

        Args:
            content: Text or markdown body to display in the chat UI.
            message_type: One of ``text``, ``code``, ``error``, ``success``,
                ``warning``, ``info``.
            metadata: Optional extra payload attached to the message.
        """
        message = AgentMessage(
            sender="agent",
            agentName=self.name,  # type: ignore[arg-type]
            content=content,
            messageType=message_type,  # type: ignore[arg-type]
            metadata=metadata,
        )
        # Lazy import to break potential circular-import with api.routes
        from ai_qa.api.websocket import broadcast_message  # noqa: PLC0415

        await broadcast_message(message)

    async def transition_to(self, new_state: AgentState) -> None:
        """Update the agent's state and notify the frontend via WebSocket.

        The frontend reads ``sender='system'`` messages to update the step
        status indicators in the UI.

        Args:
            new_state: Target ``AgentState`` to transition into.
        """
        logger.info("Agent %s: %s → %s", self.name, self.state.value, new_state.value)
        self.state = new_state
        status_msg = AgentMessage(
            sender="system",
            agentName=self.name,  # type: ignore[arg-type]
            content=new_state.value,
            messageType="info",
            metadata={"state": new_state.value, "step": self.step_number},
        )
        # Lazy import to break potential circular-import with api.routes
        from ai_qa.api.websocket import broadcast_message  # noqa: PLC0415

        await broadcast_message(status_msg)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Core agent processing logic — must be implemented by every subclass.

        Args:
            input_data: Data supplied by the user when calling ``/api/start``.
                On reject-loops this will be an empty dict; use *feedback* instead.
            feedback: User rejection feedback for re-processing.  ``None`` on
                the first pass.

        Returns:
            :class:`~ai_qa.models.StageResult` with ``success``, ``data``,
            ``errors``, ``warnings``, and ``confidence``.

        Raises:
            :class:`~ai_qa.exceptions.PipelineError`: If an unrecoverable error
                occurs inside the agent.
        """
        ...  # pragma: no cover

    # ------------------------------------------------------------------
    # Lifecycle entry points (called by API routes)
    # ------------------------------------------------------------------

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Entry point called by ``POST /api/start``.

        Transitions: START → PROCESSING → REVIEW_REQUEST | ERROR.

        Args:
            input_data: Payload from the start request body.
        """
        await self.transition_to(AgentState.PROCESSING)
        try:
            result = await self.process(input_data, feedback=None)
        except PipelineError as exc:
            logger.error("Agent %s raised PipelineError: %s", self.name, exc)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if result.success:
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content=self._format_review_content(result),
                message_type="text",
                metadata={"result": result.model_dump()},
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )

    async def handle_approve(self) -> None:
        """Called by ``POST /api/approve``.  Transitions to DONE."""
        await self.transition_to(AgentState.DONE)
        await self.send_message(
            content=f"✓ {self.step_title} complete. Ready to continue.",
            message_type="success",
        )

    async def handle_reject(self, feedback: str) -> None:
        """Called by ``POST /api/reject``.  Re-processes with feedback context.

        Transitions: current → PROCESSING → REVIEW_REQUEST | ERROR.

        Args:
            feedback: User-supplied rejection reason.
        """
        await self.send_message(
            content=f'Understood. I\'ll incorporate your feedback: "{feedback}"',
            message_type="text",
        )
        await self.transition_to(AgentState.PROCESSING)
        try:
            result = await self.process(input_data={}, feedback=feedback)
        except PipelineError as exc:
            logger.error("Agent %s raised PipelineError during reject: %s", self.name, exc)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]),
                message_type="error",
            )
            return

        if result.success:
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content=self._format_review_content(result),
                message_type="text",
                metadata={"result": result.model_dump()},
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors),
                message_type="error",
            )

    # ------------------------------------------------------------------
    # Formatting helpers (overridable in subclasses)
    # ------------------------------------------------------------------

    def _format_review_content(self, result: StageResult) -> str:
        """Format a StageResult for display in the Review Request message.

        Override in subclasses to provide richer, agent-specific output.
        """
        if result.warnings:
            return f"Review ready. {len(result.warnings)} warning(s) to note."
        return "Review ready."

    def _format_error_message(self, errors: list[str]) -> str:
        """Format errors into the three-part UX-DR12 error structure.

        Structure:  What happened / Why / What to do.
        """
        error_text = errors[0] if errors else "An unexpected error occurred"
        return (
            f"**What happened:** {error_text}\n\n"
            f"**Why:** The operation could not be completed successfully.\n\n"
            f"**What to do:** Check your input and try again, or contact support "
            f"if the problem persists."
        )
