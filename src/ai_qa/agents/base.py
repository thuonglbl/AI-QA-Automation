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
import logging
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any

from ai_qa.ai_connection.config import LLMConfig

# Local
from ai_qa.models import AgentMessage, StageResult
from ai_qa.pipelines.context import PipelineContext

logger = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def set_user_context(self, user_email: str | None) -> None:
        """Set or update the user context (legacy support)."""
        self._user_email = user_email

    def set_project_context(self, context: PipelineContext | None) -> None:
        """Attach authorized project context for project-scoped execution."""
        self.project_context = context
        if context is not None:
            self._user_email = context.user_email
            self._load_agent_config()

    # ------------------------------------------------------------------
    # Agent configuration
    # ------------------------------------------------------------------

    def _load_agent_config(self) -> None:
        """Load per-agent config from database.

        Keys in `ai_agents_config` are agent names in **lowercase**.
        """
        if not self.project_context or not self.project_context.artifact_service:
            return

        db = self.project_context.artifact_service.db

        # Lazy import to avoid circular dependency
        from ai_qa.db.models import User

        user = db.get(User, self.project_context.user_id)
        if user:
            from typing import cast

            if user.ai_agents_config:
                self._agent_config = cast(
                    dict[str, Any], user.ai_agents_config.get(self.name.lower(), {})
                )
            if user.ai_provider_config:
                self._provider_config = cast(dict[str, Any], user.ai_provider_config)
            logger.info("Loaded agent config for %s from database", self.name)
        else:
            logger.info(
                "No ai_agents_config found in database for user, using defaults for %s", self.name
            )

    # ------------------------------------------------------------------
    # Agent LLM Configuration
    # ------------------------------------------------------------------

    def get_llm_config(self) -> "LLMConfig":
        """Build LLMConfig for this agent using database configuration."""
        import os

        # Get api key from provider config
        api_key = ""
        provider_config = getattr(self, "_provider_config", {})
        credential_ref = provider_config.get("credential_reference", "")
        if credential_ref.startswith("env://"):
            env_var = credential_ref[6:]
            api_key = os.getenv(env_var, "")
        else:
            api_key = credential_ref

        return LLMConfig(
            provider=provider_config.get("provider", "litellm"),
            model_name=self._agent_config.get("model", "claude-sonnet-4-6"),
            temperature=self._agent_config.get("temperature", 0.0),
            base_url=provider_config.get("endpoint", ""),
            api_key=api_key,
            max_retries=3,
        )

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
        except Exception as exc:
            logger.error("Agent %s raised error: %s", self.name, exc, exc_info=True)
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

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
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
        except Exception as exc:
            logger.error("Agent %s raised error during reject: %s", self.name, exc, exc_info=True)
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
