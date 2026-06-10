"""Alice Agent — AI Provider Selection & Configuration.

Alice is the first step in the pipeline. She guides users through selecting
an AI provider, configuring credentials, testing the connection, and setting
up model assignments for all subsequent agents.

Lifecycle:
    Start → Processing (connection test) → Review Request → Done
                ↓
         (Reject + feedback)
                ↓
         Back to Start

Usage:
    from ai_qa.agents.alice import AliceAgent
    alice = AliceAgent()
    await alice.handle_start({"provider": "claude", "credentials": {...}})
"""

# Standard library
import ast
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

# Local
from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.ai_connection.providers import (
    ConnectionResult,
    get_provider_adapter,
    get_provider_benchmark,
    resolve_base_url,
)
from ai_qa.config import AppSettings
from ai_qa.exceptions import LLMRateLimitError, PipelineError, PipelineSilentAbortError
from ai_qa.models import (
    AgentModelConfig,
    AgentsConfig,
    AliceConfiguration,
    ProviderConfig,
    StageResult,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Provider Configuration
# =============================================================================

PROVIDER_OPTIONS: list[dict[str, Any]] = [
    {
        "id": "browser-use-cloud",
        "name": "Browser Use Cloud",
        "description": "Cloud · Personal API key",
        "quality_rank": 1,
        "security_level": "cloud",
        "credential_fields": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True}
        ],
        "endpoint_setting": "browser_use_cloud_url",
        "env_key": "BROWSER_USE_API_KEY",
    },
    {
        "id": "claude",
        "name": "Anthropic / Claude",
        "description": "Cloud · Enterprise API key or SSO",
        "quality_rank": 2,
        "security_level": "enterprise",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your Claude API key...",
            }
        ],
        "endpoint_setting": "claude_api_base_url",
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "gemini",
        "name": "Google / Gemini",
        "description": "Cloud · Personal API key",
        "quality_rank": 3,
        "security_level": "good",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your Google Gemini API key...",
            }
        ],
        "endpoint_setting": "gemini_api_base_url",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI / ChatGPT",
        "description": "Cloud · Personal API key",
        "quality_rank": 4,
        "security_level": "good",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your OpenAI API key...",
            }
        ],
        "endpoint_setting": "openai_api_base_url",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "on-premises",
        "name": "On-Premises",
        "description": "Internal infrastructure · Company API key",
        "quality_rank": 5,
        "security_level": "highest",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your on-premises API key...",
            },
        ],
        "endpoint_setting": "on_premises_api_base_url",
        "env_key": "ON_PREMISES_AI_SERVER_KEY",
    },
]


# Agent purposes for display
AGENT_PURPOSES: dict[str, str] = {
    "bob": "Requirements conversion from Confluence and Jira",
    "mary": "Test case generation",
    "sarah": "Test script generation with browser automation",
    "jack": "Test execution and analysis",
}

# Tool assignments per agent
AGENT_TOOLS: dict[str, list[str]] = {
    "bob": ["confluence_reader", "content_parser"],
    "mary": ["test_case_extractor"],
    "sarah": ["script_generator", "browser_agent"],
    "jack": ["script_runner"],
}

# Prompt templates per agent
AGENT_PROMPT_TEMPLATES: dict[str, str] = {
    "bob": "test_extraction_v1",
    "mary": "test_case_generation_v1",
    "sarah": "script_generation_v1",
    "jack": "execution_analysis_v1",
}


class AliceAgent(BaseAgent):
    """Alice Agent — AI Provider Selection & Configuration.

    Alice guides users through:
    1. Provider selection (Browser Use Cloud, Claude, Gemini/ChatGPT, On-Premises)
    2. Credential configuration
    3. Connection testing
    4. Model assignment review
    5. Configuration persistence

    Attributes:
        _selected_provider: Currently selected provider ID
        _provider_credentials: Stored credentials for selected provider
        _configuration: Complete AliceConfiguration after approval
    """

    def __init__(self) -> None:
        """Initialize Alice Agent."""
        super().__init__(
            name="Alice",
            color="#EC4899",  # Pink per UX-DR19
            step_number=1,
            step_title="AI Provider Configuration",
        )
        self._selected_provider: str | None = None
        self._provider_credentials: dict[str, str] = {}
        self._configuration: AliceConfiguration | None = None
        self._model_reasoning: list[dict[str, str]] = []
        self._settings = AppSettings()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def check_existing_configuration(self) -> AliceConfiguration | None:
        """Check for existing valid configuration in DB.

        Returns:
            AliceConfiguration if valid config exists, None otherwise
        """
        if not self.project_context or not self.project_context.thread_id:
            return None

        if not self.project_context.artifact_service:
            return None

        db = self.project_context.artifact_service.db
        from ai_qa.threads.models import Thread

        thread = db.get(Thread, self.project_context.thread_id)
        if not thread or not thread.provider_name:
            return None

        try:
            # Reconstruct the expected configurations from the Thread
            provider_config = ProviderConfig(
                provider=thread.provider_name,
                provider_name=thread.provider_name.capitalize(),
                endpoint=thread.provider_base_url or "",
                credential_reference="",  # Loaded from user directly via base.py now
                tested_at="",
                test_result="success",
            )

            # Build agents config — tolerate both structured dict and legacy flat string.
            # Structured: {"model": str, "temperature": float, "rationale": str}
            # Legacy:     "model-id-string"
            agents_dict: dict[str, Any] = {}
            loaded_reasoning: list[dict[str, str]] = []
            for agent_name, agent_cfg in (thread.agent_configs or {}).items():
                if isinstance(agent_cfg, dict):
                    model_name = agent_cfg.get("model") or agent_cfg.get("model_name")
                    temperature = float(agent_cfg.get("temperature", 0.0))
                    rationale = str(agent_cfg.get("rationale", ""))
                else:
                    model_name = agent_cfg if isinstance(agent_cfg, str) else None
                    temperature = 0.0
                    rationale = ""
                agents_dict[agent_name.lower()] = {
                    "model": model_name,
                    "temperature": temperature,
                    "prompt_template": "default",
                    "tools": [],
                }
                if rationale:
                    loaded_reasoning.append(
                        {
                            "agent": agent_name.lower(),
                            "model": model_name or "",
                            "rationale": rationale,
                        }
                    )

            # Ensure Alice config exists
            if "alice" not in agents_dict:
                agents_dict["alice"] = {
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.0,
                    "prompt_template": "default",
                    "tools": [],
                }

            # Restore rationale into _model_reasoning so the inspect view shows real values
            if loaded_reasoning:
                self._model_reasoning = loaded_reasoning

            agents_config = AgentsConfig.model_validate({"updated_at": "", "agents": agents_dict})

            return AliceConfiguration(provider=provider_config, agents=agents_config)
        except Exception as exc:
            logger.warning("Failed to load existing configuration from DB: %s", exc)
            return None

    def get_provider_options(self) -> list[dict[str, Any]]:
        """Get provider options for frontend display.

        Returns:
            List of provider option dictionaries
        """
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p.get("description", ""),
                "quality_rank": p["quality_rank"],
                "security_level": p["security_level"],
                "credential_fields": p["credential_fields"],
            }
            for p in PROVIDER_OPTIONS
        ]

    def get_on_prem_defaults(self) -> dict[str, object]:
        """Return non-secret on-premises defaults (status only — never the key).

        Returns:
            Dict with ``server_url`` (str) and ``api_key_configured`` (bool).
            Never returns the decrypted API key (FR57 / FR58 / Task 10).
        """
        if self.project_context and self.project_context.artifact_service:
            db = self.project_context.artifact_service.db
            from ai_qa.secrets import SECRET_TYPE_ON_PREMISES
            from ai_qa.secrets.service import get_user_secret

            server_url = ""
            if self.project_context.thread_id:
                from ai_qa.threads.models import Thread

                thread = db.get(Thread, self.project_context.thread_id)
                if thread and thread.provider_base_url:
                    server_url = thread.provider_base_url

            stored = get_user_secret(db, self.project_context.user_id, SECRET_TYPE_ON_PREMISES)
            return {
                "server_url": server_url,
                "api_key_configured": bool(stored),
            }
        return {"server_url": "", "api_key_configured": False}

    # -------------------------------------------------------------------------
    # BaseAgent Interface
    # -------------------------------------------------------------------------

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Process Alice step logic.

        Args:
            input_data: Provider selection and credentials
            feedback: User rejection feedback (for re-processing)

        Returns:
            StageResult with configuration data on success

        Raises:
            PipelineError: If connection test fails or invalid input
        """
        # Handle feedback/reject case
        if feedback:
            logger.info("Alice received feedback: %s", feedback)
            # Return to start state for re-selection
            return StageResult(
                success=True,
                data={"action": "restart_selection", "feedback": feedback},
            )

        # Extract provider selection and credentials
        provider_id = input_data.get("provider")
        credentials = input_data.get("credentials", {})

        if not provider_id:
            raise PipelineError("No provider selected")

        # Validate provider
        provider_info = self._get_provider_info(provider_id)
        if not provider_info:
            raise PipelineError(f"Unknown provider: {provider_id}")

        self._selected_provider = provider_id
        self._provider_credentials = credentials
        self._model_reasoning = []

        # Immediately update the thread with the provider info so it's not null in the DB
        # even if the connection test or LLM assignment fails later.
        if (
            self.project_context
            and self.project_context.artifact_service
            and self.project_context.thread_id
        ):
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.threads.models import Thread

                thread = db.get(Thread, self.project_context.thread_id)
                if thread:
                    thread.provider_name = provider_id
                    thread.provider_base_url = provider_info.get("endpoint", "")
                    db.commit()
            except Exception as e:
                logger.warning("Failed to save initial provider info to DB: %s", e)

        # For on-prem with blank api_key, resolve the stored secret BEFORE the connection
        # test so the adapter receives the real key (Task 10 fix — ordering bug).
        _original_api_key = credentials.get("api_key", "").strip()
        if provider_info["id"] == "on-premises" and not _original_api_key:
            if self.project_context and self.project_context.artifact_service:
                try:
                    from ai_qa.secrets import SECRET_TYPE_ON_PREMISES
                    from ai_qa.secrets.service import get_user_secret

                    _stored = get_user_secret(
                        self.project_context.artifact_service.db,
                        self.project_context.user_id,
                        SECRET_TYPE_ON_PREMISES,
                    )
                    if _stored:
                        credentials = {**credentials, "api_key": _stored}
                except Exception as _pre_e:
                    logger.warning("Failed to resolve stored on-prem key for test: %s", _pre_e)

        # Test connection
        await self._send_connection_test_status(
            "testing", f"Testing connection to {provider_info['name']}..."
        )

        try:
            connection_result = await self._test_connection(provider_info, credentials)
        except Exception as exc:
            logger.error("Connection test failed: %s", exc)
            connection_result = ConnectionResult(
                success=False,
                provider=provider_info["id"],
                provider_name=provider_info["name"],
                status="failed",
                message=(
                    f"Could not validate the connection to {provider_info['name']}. "
                    "Please check your credentials and try again."
                ),
                error_category="provider_error",
            )

        if not connection_result.success:
            await self._send_connection_test_status("failed", connection_result.message)
            raise PipelineError(connection_result.message)

        # Persist credentials if user is authenticated.
        # Use _original_api_key (pre-resolution) so a reused stored key is never
        # re-written back to storage (Task 10).
        if self.project_context and self.project_context.artifact_service:
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
                from ai_qa.secrets.service import set_user_secret

                secret_type = PROVIDER_SECRET_TYPE_MAP.get(provider_info["id"])
                if secret_type and _original_api_key:
                    set_user_secret(
                        db, self.project_context.user_id, secret_type, _original_api_key
                    )
                    db.commit()
            except Exception as e:
                logger.warning("Failed to persist user credentials: %s", e)

        # Generate configuration
        self._configuration = await self._generate_configuration(provider_info, credentials)

        # Return result with model assignments for review
        return StageResult(
            success=True,
            data={
                "configuration": self._configuration.model_dump(),
                "model_assignments": self._get_model_assignments_display(),
                "provider_endpoint": self._mask_endpoint(self._configuration.provider.endpoint),
                "benchmark": get_provider_benchmark(provider_id),
            },
        )

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override handle_start to support existing configuration check."""
        if not self.project_context or not self.project_context.artifact_service:
            return

        db = self.project_context.artifact_service.db

        # 1. Project selection logic if thread is unbound
        if self.project_context.project_id is None:
            if input_data.get("project_id"):
                # Bind project
                from uuid import UUID

                from ai_qa.threads.service import ThreadService

                try:
                    project_id = UUID(str(input_data["project_id"]))
                except ValueError:
                    logger.error("Invalid project_id UUID format: %s", input_data.get("project_id"))
                    await self.send_message(
                        content="Invalid project selection payload format.",
                        message_type="error",
                    )
                    return

                thread_id = self.project_context.thread_id
                if not thread_id:
                    raise PipelineError("No thread_id in context")

                thread_service = ThreadService(db)
                try:
                    thread_service.bind_project(thread_id, project_id, self.project_context.user_id)
                    self.project_context.project_id = project_id
                except Exception as e:
                    logger.error("Failed to bind project to thread: %s", e)
                    await self.send_message(
                        content=f"Failed to bind project: {e}",
                        message_type="error",
                    )
                    return
            else:
                # Need to prompt for project selection
                from ai_qa.projects.service import get_user_projects

                projects = get_user_projects(db, self.project_context.user_id)
                if not projects:
                    await self.send_message(
                        content="You are not a member of any projects. Please ask an administrator to add you to a project before continuing.",
                        message_type="error",
                    )
                    return
                elif len(projects) == 1:
                    # Auto-bind if exactly 1 project
                    from ai_qa.threads.service import ThreadService

                    project_id = projects[0].id
                    thread_id = self.project_context.thread_id
                    if thread_id:
                        thread_service = ThreadService(db)
                        try:
                            thread_service.bind_project(
                                thread_id, project_id, self.project_context.user_id
                            )
                            self.project_context.project_id = project_id

                            await self.send_message(
                                content=f"Auto-bound to your only project: {projects[0].name}",
                                message_type="info",
                                metadata={
                                    "type": "project_auto_bind",
                                    "project_id": str(project_id),
                                    "project_name": projects[0].name,
                                },
                            )
                        except Exception as e:
                            logger.error("Failed to auto-bind project: %s", e)
                            await self.send_message(
                                content=f"Failed to auto-bind project: {e}",
                                message_type="error",
                            )
                            return
                    else:
                        raise PipelineError("No thread_id in context")
                else:
                    # Present options
                    project_options = [{"id": str(p.id), "name": p.name} for p in projects]
                    await self.send_message(
                        content="Please select a project for this conversation:",
                        message_type="info",
                        metadata={
                            "type": "project_selection",
                            "projects": project_options,
                        },
                    )
                    return  # Stop processing until frontend sends project_id back

        # 2. Check existing thread configuration (resume same thread)
        existing_config = await self.check_existing_configuration()

        if existing_config and not input_data.get("force_reconfigure"):
            # Use existing thread configuration — this is a RESUME, not a saved-config prompt.
            self._configuration = existing_config
            self._selected_provider = existing_config.provider.provider

            # Show review with existing config
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content=self._format_model_assignments(existing_config),
                message_type="text",
                metadata={
                    "configuration": existing_config.model_dump(),
                    "model_assignments": self._get_model_assignments_from_config(
                        existing_config, self._model_reasoning
                    ),
                    "provider_endpoint": self._mask_endpoint(existing_config.provider.endpoint),
                },
            )
            return

        # Handle explicit "use saved configuration" response from frontend
        if input_data.get("use_saved_config") and not input_data.get("force_reconfigure"):
            if (
                self.project_context
                and self.project_context.artifact_service
                and self.project_context.project_id  # F3: project must be bound
            ):
                db = self.project_context.artifact_service.db
                from ai_qa.userconfig.service import get_provider_config

                saved = get_provider_config(
                    db, self.project_context.user_id, self.project_context.project_id
                )
                if saved:
                    try:
                        prov = saved["provider"] or {}
                        saved_provider_id_s = prov.get("provider", "")
                        if not saved_provider_id_s:  # F4: reject empty provider
                            raise ValueError("Saved config has no provider id")
                        agt = saved["agents"] or {}
                        raw_agents_s = agt.get("agents") or {}
                        agents_dict_s: dict[str, Any] = {}
                        for agent_name, cfg_s in raw_agents_s.items():
                            agents_dict_s[agent_name] = {
                                "model": cfg_s.get("model"),
                                "temperature": float(cfg_s.get("temperature", 0.0)),
                                "prompt_template": cfg_s.get("prompt_template", "default"),
                                "tools": cfg_s.get("tools", []),
                            }
                        if not agents_dict_s:  # F5: reject empty agent assignments
                            raise ValueError("Saved config has no agent assignments")
                        if "alice" not in agents_dict_s:
                            agents_dict_s["alice"] = {
                                "model": "claude-3-5-sonnet-20241022",
                                "temperature": 0.0,
                                "prompt_template": "default",
                                "tools": [],
                            }
                        # F2: restore _model_reasoning so _save_configuration writes real
                        # rationale into the new thread snapshot (not empty strings).
                        self._model_reasoning = [
                            {
                                "agent": n,
                                "model": cfg_s.get("model", ""),
                                "rationale": cfg_s.get("rationale", ""),
                            }
                            for n, cfg_s in raw_agents_s.items()
                        ]
                        from ai_qa.models import AgentsConfig, AliceConfiguration, ProviderConfig

                        loaded_config = AliceConfiguration(
                            provider=ProviderConfig(
                                provider=saved_provider_id_s,
                                provider_name=prov.get("provider_name", ""),
                                endpoint=prov.get("endpoint", ""),
                                credential_reference="",
                                tested_at=prov.get("tested_at", ""),
                                test_result=prov.get("test_result", "success"),
                            ),
                            agents=AgentsConfig.model_validate(
                                {"updated_at": "", "agents": agents_dict_s}
                            ),
                        )
                        self._configuration = loaded_config
                        self._selected_provider = loaded_config.provider.provider
                        self._save_configuration(loaded_config)
                        await self.transition_to(AgentState.DONE)
                        return
                    except Exception as exc:
                        logger.warning("Failed to apply saved config: %s", exc)
            # F7+F8: show provider options directly — do NOT fall through to the
            # saved-config prompt block, which would re-offer the same config.
            await self.send_message(
                content="Saved configuration could not be applied. Please select a provider.",
                message_type="info",
            )
            await self.send_message(
                content="Please select your AI provider:",
                message_type="info",
                metadata={
                    "type": "provider_options",
                    "options": self.get_provider_options(),
                    "on_prem_defaults": self.get_on_prem_defaults(),
                },
            )
            return

        # Check if there is a valid saved (user, project) config to offer explicitly
        if (
            not input_data.get("provider")
            and not input_data.get("force_reconfigure")
            and self.project_context
            and self.project_context.artifact_service
            and self.project_context.project_id
        ):
            db = self.project_context.artifact_service.db
            from ai_qa.userconfig.service import get_provider_config

            saved_cfg = get_provider_config(
                db, self.project_context.user_id, self.project_context.project_id
            )
            if saved_cfg and saved_cfg.get("provider"):
                saved_provider_id = (saved_cfg["provider"] or {}).get("provider", "")
                # Validity check: provider in project.enabled_providers AND secret configured
                from ai_qa.db.models import Project
                from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
                from ai_qa.secrets.service import get_user_secret

                project = db.get(Project, self.project_context.project_id)
                enabled = (project.enabled_providers if project else []) or []
                provider_allowed = not enabled or saved_provider_id in enabled
                secret_type = PROVIDER_SECRET_TYPE_MAP.get(saved_provider_id)
                secret_ok = bool(
                    secret_type and get_user_secret(db, self.project_context.user_id, secret_type)
                )
                if provider_allowed and secret_ok:
                    prov_meta = saved_cfg["provider"] or {}
                    agt_meta = (saved_cfg.get("agents") or {}).get("agents") or {}
                    agents_summary = [
                        {
                            "agent": n,
                            "model": v.get("model", ""),
                            "rationale": v.get("rationale", ""),
                        }
                        for n, v in agt_meta.items()
                    ]
                    await self.send_message(
                        content="You have a saved provider configuration for this project.",
                        message_type="info",
                        metadata={
                            "type": "saved_config_prompt",
                            "saved_config": {
                                "provider_name": prov_meta.get("provider_name", ""),
                                "endpoint": self._mask_endpoint(prov_meta.get("endpoint", "")),
                                "agents": agents_summary,
                            },
                            "options": self.get_provider_options(),
                            "enabled_providers": enabled,
                        },
                    )
                    return

        # Check if user already selected provider (frontend sent provider in input_data)
        if input_data.get("provider"):
            # User already selected provider, skip greeting and go straight to processing
            await self.transition_to(AgentState.PROCESSING)
            try:
                result = await self.process(input_data, feedback=None)
            except PipelineSilentAbortError:
                return
            except PipelineError as exc:
                logger.error("Alice process failed: %s", exc)
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
                    metadata=result.data,
                )
            else:
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message(result.errors),
                    message_type="error",
                )
        else:
            # No provider selected yet - show greeting and provider options
            await self.send_message(
                content="Hi! I'm Alice. Let's set up your AI provider so we can get started with test automation. "
                "I'll help you choose the best provider for your needs and configure the models for each agent.",
                message_type="text",
            )

            # Send provider options
            await self.send_message(
                content="Please select your AI provider:",
                message_type="info",
                metadata={
                    "type": "provider_options",
                    "options": self.get_provider_options(),
                    "on_prem_defaults": self.get_on_prem_defaults(),
                },
            )

    def _format_error_message(self, errors: list[str]) -> str:
        """Override base error formatting to remove generic text for Rate Limit errors."""
        error_text = errors[0] if errors else "An unexpected error occurred"
        if "Rate Limit Error:" in error_text:
            return (
                f"**What happened:** {error_text}\n\n"
                f"**What to do:** Please check your provider subscription plan and billing details, or create a new thread using a different API key."
            )
        return super()._format_error_message(errors)

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Save configuration and complete Alice step."""
        if self._configuration is None:
            logger.error("Cannot approve - no configuration generated")
            await self.send_message(
                content="Error: No configuration to approve. Please start over.",
                message_type="error",
            )
            return

        if data and "assignments" in data:
            for agent_name, new_model in data["assignments"].items():
                if agent_name in self._configuration.agents.agents:
                    self._configuration.agents.agents[agent_name].model = new_model

        # Save configuration files
        try:
            self._save_configuration(self._configuration)
        except OSError as exc:
            logger.error("Failed to save configuration: %s", exc)
            await self.send_message(
                content=f"Failed to save configuration: {exc}",
                message_type="error",
            )
            await self.transition_to(AgentState.ERROR)
            return

        # Persist non-secret config per (user, project) for future threads
        if (
            self.project_context
            and self.project_context.artifact_service
            and self.project_context.project_id
        ):
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.userconfig.service import save_provider_config

                provider_cfg = {
                    "provider": self._configuration.provider.provider,
                    "provider_name": self._configuration.provider.provider_name,
                    "endpoint": self._configuration.provider.endpoint,
                    "tested_at": self._configuration.provider.tested_at,
                    "test_result": self._configuration.provider.test_result,
                    "rationale": "",
                }
                reasoning_map = {
                    r["agent"]: r.get("rationale", "")
                    for r in self._model_reasoning
                    if isinstance(r, dict) and "agent" in r
                }
                agents_cfg: dict[str, Any] = {"version": "1", "updated_at": "", "agents": {}}
                for name, cfg in self._configuration.agents.agents.items():
                    agents_cfg["agents"][name] = {
                        "model": cfg.model,
                        "temperature": cfg.temperature,
                        "prompt_template": cfg.prompt_template,
                        "tools": list(cfg.tools),
                        "rationale": reasoning_map.get(name, ""),
                    }
                save_provider_config(
                    db,
                    self.project_context.user_id,
                    self.project_context.project_id,
                    provider_cfg,
                    agents_cfg,
                )
                db.commit()
            except Exception as exc:
                logger.warning("Failed to persist per-project provider config: %s", exc)

        await self.transition_to(AgentState.DONE)

    async def handle_reject(self, feedback: str) -> None:
        """Reject the model assignment review and return to provider configuration.

        Does NOT persist any approved configuration. Only creates a conversational
        acknowledgment message and resets the thread to configuration adjustment.
        """
        await self.send_message(
            content="Understood. Let's adjust your provider configuration.",
            message_type="text",
        )
        # Clear generated configuration so re-selection starts fresh
        self._configuration = None
        self._model_reasoning = []
        await self.transition_to(AgentState.START)
        # Re-show provider options so the user can reconfigure
        await self.send_message(
            content="Please select your AI provider:",
            message_type="info",
            metadata={
                "type": "provider_options",
                "options": self.get_provider_options(),
                "on_prem_defaults": self.get_on_prem_defaults(),
            },
        )

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _assign_fallback_models(self, models_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Per-agent capability preferences (ordered keyword hints).
        # Uses first matching hint (deterministic) — no randomization.
        fallback_models = {
            "Alice": ["claude-3-5-sonnet", "gpt-4o", "pro", "sonnet"],
            "Bob": ["opus", "gpt-4o", "gpt-5", "pro", "vision", "sonnet"],
            "Mary": ["sonnet", "gpt-4", "pro", "flash"],
            "Sarah": ["opus", "coder", "sonnet", "gpt-4", "pro"],
            "Jack": ["haiku", "mini", "flash", "lite", "sonnet"],
        }

        reasoning = []
        for agent, candidates in fallback_models.items():
            assigned_model = None
            for candidate in candidates:
                if any(candidate in m["id"].lower() for m in models_list):
                    assigned_model = next(
                        m["id"] for m in models_list if candidate in m["id"].lower()
                    )
                    break

            # Fallback to the first available model if no hint matched
            if not assigned_model and models_list:
                assigned_model = models_list[0]["id"]

            if not assigned_model:
                assigned_model = "Unavailable"

            reasoning.append(
                {
                    "agent": agent,
                    "purpose": AGENT_PURPOSES.get(agent, ""),
                    "model": assigned_model,
                    "reasoning": "Fallback selection due to empty or rate-limited models.",
                }
            )
        return reasoning

    def _get_provider_info(self, provider_id: str) -> dict[str, Any] | None:
        """Get provider info by ID."""
        for p in PROVIDER_OPTIONS:
            if p["id"] == provider_id:
                info = p.copy()
                setting_name = info.get("endpoint_setting")
                if setting_name:
                    # Resolve the config-owned base URL through the registry so the
                    # provider adapters and Alice share a single source of truth
                    # (avoids drift between PROVIDER_OPTIONS and the registry map).
                    info["endpoint"] = resolve_base_url(self._settings, provider_id)
                return info
        return None

    async def _test_connection(
        self, provider_info: dict[str, Any], credentials: dict[str, str]
    ) -> ConnectionResult:
        """Test connection to provider via its adapter.

        Delegates auth + reachability validation to the provider adapter, which
        owns the on-prem config guard, the api-key format floor, and all
        provider-specific header/endpoint details. Base URLs are config-owned
        (resolved via ``resolve_base_url`` in ``_get_provider_info``); credentials
        are passed in by the caller.

        Args:
            provider_info: Provider configuration (includes config-owned endpoint)
            credentials: User-provided credentials

        Returns:
            A normalized, secret-free ``ConnectionResult``.
        """
        provider_id = provider_info["id"]
        endpoint = provider_info.get("endpoint", "")
        adapter = get_provider_adapter(provider_id)
        result = await adapter.validate_connection(
            {"api_key": credentials.get("api_key", "")}, endpoint
        )
        if result.success:
            logger.info("Connection test passed for %s", provider_info["name"])
        return result

    async def _simulate_delay(self, seconds: float) -> None:
        """Simulate processing delay."""
        import asyncio

        await asyncio.sleep(seconds)

    async def _send_connection_test_status(self, status: str, message: str) -> None:
        """Send connection test status update."""
        await self.send_message(
            content=message,
            message_type="info" if status != "failed" else "error",
            metadata={
                "type": "connection_test",
                "status": status,
                "message": message,
            },
        )

    async def _generate_configuration(
        self, provider_info: dict[str, Any], credentials: dict[str, str]
    ) -> AliceConfiguration:
        """Generate complete configuration for selected provider.

        Args:
            provider_info: Selected provider info
            credentials: User credentials

        Returns:
            Complete AliceConfiguration
        """
        provider_id = provider_info["id"]
        now = datetime.now(UTC).isoformat()

        # Determine endpoint
        endpoint = provider_info.get("endpoint", "")
        api_key = credentials.get("api_key", "")

        # 1. Discover available models via the provider adapter (Story 9.4).
        #    Discovery runs only after a successful validate_connection in
        #    process(), so the AC1 precondition is satisfied. The adapter returns
        #    the raw discovered set; Alice owns ranking/assignment + the gate.
        adapter = get_provider_adapter(provider_id)
        discovered = await adapter.list_models({"api_key": api_key}, endpoint)

        # Categorize models into available and unavailable
        available_models: list[dict[str, Any]] = []
        unavailable_models: list[dict[str, Any]] = []

        unsupported_keywords = [
            "embed",
            "tts",
            "whisper",
            "audio",
            "dall-e",
            "babbage",
            "davinci",
            "instruct",
            "realtime",
            "moderation",
            "text-search",
            "text-similarity",
            "code-search",
            "edit",
        ]

        for dm in discovered:
            # Match whole words or prefixed segments to avoid false positives
            # e.g., "embedding" should match "text-embedding-ada-002" but not "my-embedding-model"
            is_unsupported = any(
                kw == dm.id.lower()
                or dm.id.lower().startswith(kw + "-")
                or dm.id.lower().endswith("-" + kw)
                or f"-{kw}-" in dm.id.lower()
                for kw in unsupported_keywords
            )

            if is_unsupported:
                unavailable_models.append(
                    {"id": dm.id, "name": dm.display_name, "status": "not support / outdated"}
                )
            else:
                available_models.append({"id": dm.id, "name": dm.display_name})

        if not available_models:
            # Emit trace to show the models that were discovered but unavailable
            fallback_assignments = self._assign_fallback_models(unavailable_models)
            error_trace = {
                "connection_status": "success",
                "available_models": [],
                "unavailable_models": unavailable_models,
                "chain_of_thought": [
                    "[What happened] No available models were found. "
                    "The provider may have rejected model-listing requests (check that your "
                    "key has model-listing permissions) or no models match your credentials.",
                    "[What to do] Verify your API key has access to list models, "
                    "then create a new thread to try again.",
                ],
                "assignments": fallback_assignments,
            }
            await self.send_message(
                content="Finished model assignment reasoning.",
                message_type="info",
                metadata={"type": "thinking_trace", "trace": error_trace},
            )

            # Transition to ERROR and abort silently to prevent plaintext bubble
            await self.transition_to(AgentState.ERROR)
            raise PipelineSilentAbortError()

        # 2. Bootstrap Alice model
        alice_model, alice_rationale = self._bootstrap_alice_model(available_models)
        if not alice_model:
            raise PipelineError(
                "No available model to proceed. Please check your subscription then create a new thread to continue."
            )

        # 3. Assign models via LLM
        try:
            model_mappings, reasoning = await self._assign_models_via_llm(
                provider_id, endpoint, api_key, alice_model, available_models
            )
        except PipelineError as e:
            error_str = str(e)
            formatted_message = error_str

            # Try to format the ugly Litellm JSON error nicely
            if "LLM rate limit error" in error_str or "Error code:" in error_str:
                # Move all available models to unavailable models
                for m in available_models:
                    unavailable_models.append(
                        {"id": m["id"], "name": m["name"], "status": "rate limit"}
                    )
                available_models.clear()

                match = re.search(r"Error code: \d+ - (.*)", error_str)
                if match:
                    try:
                        parsed = ast.literal_eval(match.group(1).strip())
                        if isinstance(parsed, list) and len(parsed) > 0:
                            parsed = parsed[0]
                        if (
                            isinstance(parsed, dict)
                            and "error" in parsed
                            and "message" in parsed["error"]
                        ):
                            formatted_message = f"Rate Limit Error: {parsed['error']['message']}"
                    except Exception:
                        msg_match = re.search(r"'message':\s*'([^']+)'", error_str)
                        if msg_match:
                            formatted_message = f"Rate Limit Error: {msg_match.group(1)}"

            # Determine if it's a rate limit error to provide specific guidance
            if "Rate Limit Error:" in formatted_message:
                what_happened = f"[What happened] {formatted_message}"
                what_to_do = "[What to do] Please check your provider subscription plan and billing details, or create a new thread using a different API key."
                chain_of_thought = [what_happened, what_to_do]
            else:
                chain_of_thought = [f"[What happened] {formatted_message}"]

            fallback_assignments = self._assign_fallback_models(unavailable_models)
            trace_payload: dict[str, Any] = {
                "connection_status": "success",
                "available_models": available_models,
                "unavailable_models": unavailable_models,
                "bootstrap_model": alice_model,
                "bootstrap_rationale": alice_rationale,
                "agent_needs": AGENT_PURPOSES,
                "assignments": fallback_assignments,
                "chain_of_thought": chain_of_thought,
            }
            await self.send_message(
                content="Finished model assignment reasoning.",
                message_type="info",
                metadata={"type": "thinking_trace", "trace": trace_payload},
            )

            await self.transition_to(AgentState.ERROR)
            raise PipelineSilentAbortError() from e

        # 4. Emit thinking trace
        trace_payload = {
            "connection_status": "success",
            "available_models": available_models,
            "unavailable_models": unavailable_models,
            "bootstrap_model": alice_model,
            "bootstrap_rationale": alice_rationale,
            "agent_needs": AGENT_PURPOSES,
            "assignments": reasoning,
            "benchmark": get_provider_benchmark(provider_id),
        }
        await self.send_message(
            content="Finished model assignment reasoning.",
            message_type="info",
            metadata={"type": "thinking_trace", "trace": trace_payload},
        )

        # Create provider config
        provider_config = ProviderConfig(
            provider=provider_id,
            provider_name=provider_info["name"],
            endpoint=endpoint,
            credential_reference="",
            tested_at=now,
            test_result="success",
        )

        agents: dict[str, AgentModelConfig] = {}
        # Also assign Alice her model
        agents["alice"] = AgentModelConfig(
            model=alice_model,
            temperature=0.0,
            prompt_template="default_v1",
            tools=[],
        )
        for agent_name in ["bob", "mary", "sarah", "jack"]:
            agents[agent_name] = AgentModelConfig(
                model=model_mappings.get(agent_name, alice_model),
                temperature=0.0,
                prompt_template=AGENT_PROMPT_TEMPLATES.get(agent_name, "default_v1"),
                tools=AGENT_TOOLS.get(agent_name, []),
            )

        agents_config = AgentsConfig(
            updated_at=now,
            agents=agents,
        )

        # Store rationale for display in the review panel (threaded through
        # _get_model_assignments_display / _format_model_assignments).
        self._model_reasoning = reasoning

        # Immediately update the thread with the provider info so it's not null in the DB
        # before the user approves the agent configurations.
        if (
            self.project_context
            and self.project_context.artifact_service
            and self.project_context.thread_id
        ):
            db = self.project_context.artifact_service.db
            from ai_qa.threads.models import Thread

            thread = db.get(Thread, self.project_context.thread_id)
            if thread:
                thread.provider_name = provider_id
                thread.provider_base_url = endpoint
                db.commit()

        return AliceConfiguration(provider=provider_config, agents=agents_config)

    def _save_configuration(self, config: AliceConfiguration) -> None:
        """Save configuration to Thread database."""
        if (
            not self.project_context
            or not self.project_context.artifact_service
            or not self.project_context.thread_id
        ):
            logger.error("No project context or thread_id available to save configuration.")
            raise OSError("No thread_id available to save configuration.")

        db = self.project_context.artifact_service.db
        from ai_qa.threads.models import Thread

        thread = db.get(Thread, self.project_context.thread_id)
        if thread:
            thread.provider_name = config.provider.provider
            thread.provider_base_url = config.provider.endpoint

            # Write structured per-agent entries (model + temperature + rationale)
            # so check_existing_configuration and _load_agent_config can round-trip.
            reasoning_map = {
                r["agent"]: r.get("rationale", "")
                for r in self._model_reasoning
                if isinstance(r, dict) and "agent" in r
            }
            new_configs = {}
            for agent_name, agent_cfg in config.agents.agents.items():
                new_configs[agent_name] = {
                    "model": agent_cfg.model,
                    "temperature": agent_cfg.temperature,
                    "rationale": reasoning_map.get(agent_name, ""),
                }

            thread.agent_configs = new_configs

            db.commit()
            logger.info("Configuration saved to database for thread %s", thread.id)
        else:
            raise OSError("Thread not found to save configuration.")

    def _is_config_valid(self, provider_data: dict[str, Any]) -> bool:
        """Check if existing configuration is still valid (not expired)."""
        try:
            tested_at = datetime.fromisoformat(provider_data.get("tested_at", "1970-01-01"))
            age_days = (datetime.now(UTC) - tested_at).days
            return age_days < 30
        except (ValueError, TypeError):
            return False

    def _get_model_assignments_display(self) -> list[dict[str, str]]:
        """Get model assignments for display in review (with rationale)."""
        if not self._configuration:
            return []

        return self._get_model_assignments_from_config(self._configuration, self._model_reasoning)

    def _get_model_assignments_from_config(
        self,
        config: AliceConfiguration,
        reasoning: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Get model assignments from configuration."""
        reasoning_map: dict[str, str] = {}
        if reasoning:
            for r in reasoning:
                if isinstance(r, dict) and "agent" in r and "rationale" in r:
                    reasoning_map[str(r["agent"])] = str(r["rationale"])

        assignments = []
        for agent_name, agent_config in config.agents.agents.items():
            if agent_name == "alice":
                purpose = "Provider Selection & Configuration"
            else:
                purpose = AGENT_PURPOSES.get(agent_name, "Agent task")
            agent_display = agent_name.capitalize()
            assignments.append(
                {
                    "agent": agent_display,
                    "model": agent_config.model,
                    "purpose": purpose,
                    "rationale": reasoning_map.get(agent_name, ""),
                }
            )
        return assignments

    def _bootstrap_alice_model(self, available_models: list[dict[str, Any]]) -> tuple[str, str]:
        """Bootstrap Alice's reasoning model using keyword heuristics.

        Returns:
            tuple of (model_id, rationale)
        """
        if not available_models:
            return "", ""

        model_ids = [m["id"] for m in available_models]

        # Priority keywords for high-quality reasoning
        priorities = [
            "gpt-5",
            "opus",
            "gpt-4",
            "pro-3",
            "pro",
            "sonnet",
            "deepseek-v4",
            "deepseek-v3",
            "deepseek-coder",
            "kimi",
            "glm",
            "qwen-72",
            "llama-3-70",
        ]

        for p in priorities:
            for m_id in model_ids:
                if p in str(m_id).lower():
                    return str(m_id), f"Chosen based on capability priority keyword '{p}'."

        # Fallback to first available
        return str(model_ids[0]), "Fallback to first available model."

    async def _assign_models_via_llm(
        self,
        provider_id: str,
        endpoint: str,
        api_key: str,
        alice_model: str,
        available_models: list[dict[str, Any]],
    ) -> tuple[dict[str, str], list[dict[str, str]]]:
        """Assign models for Bob, Mary, Sarah, Jack via an LLM call."""
        from langchain_core.messages import HumanMessage, SystemMessage

        from ai_qa.ai_connection.client import LLMClient
        from ai_qa.ai_connection.config import LLMConfig

        config = LLMConfig(
            provider=provider_id,
            model_name=alice_model,
            temperature=0.0,
            base_url=endpoint,
            api_key=api_key,
            max_retries=1,
        )
        try:
            client = LLMClient(config)

            system_prompt = """You are Alice, an AI configuration assistant. Your job is to assign the best available models to four specialized agents based on their needs:
- Bob: Needs strong reasoning, long-context extraction, tool-compatible output, AND vision capability (multimodal) for image captioning from Confluence pages. MUST be a vision-capable model.
- Mary: Needs structured-output and instruction-following.
- Sarah: Needs coding and tool capabilities.
- Jack: Needs fast, lower-cost summarization/execution-analysis.

Available Models:
{models_list}

IMPORTANT: Bob's model MUST support vision/multimodal input. Prefer models with known vision support (e.g., gpt-4o, gemini-1.5-pro, claude-3-5-sonnet, etc.).

Respond with a JSON object exactly in this format:
{{
  "assignments": {{
    "bob": "model_id",
    "mary": "model_id",
    "sarah": "model_id",
    "jack": "model_id"
  }},
  "reasoning": [
    {{"agent": "bob", "rationale": "reason..."}},
    {{"agent": "mary", "rationale": "reason..."}},
    {{"agent": "sarah", "rationale": "reason..."}},
    {{"agent": "jack", "rationale": "reason..."}}
  ]
}}
"""
            sys_msg = SystemMessage(
                content=system_prompt.format(
                    models_list=", ".join([m["id"] for m in available_models])
                )
            )
            human_msg = HumanMessage(content="Please assign models and provide your reasoning.")

            response = client.invoke([sys_msg, human_msg])
            response_text = str(response.content)

            # Extract JSON
            json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
            if not json_match:
                # Fallback to greedy search if no markdown block
                json_match = re.search(r"\{.*\}", response_text, re.DOTALL)

            if json_match:
                data = json.loads(
                    json_match.group(1) if json_match.groups() else json_match.group(0)
                )
                if isinstance(data, dict):
                    assignments = data.get("assignments") or {}
                    reasoning = data.get("reasoning") or []

                    # Validate models against available_models
                    valid_ids = {str(m["id"]) for m in available_models}
                    final_assignments = {}
                    final_reasoning = []

                    for agent in ["bob", "mary", "sarah", "jack"]:
                        assigned_model = str(assignments.get(agent, ""))
                        if assigned_model in valid_ids:
                            final_assignments[agent] = assigned_model
                            agent_reason = next(
                                (
                                    r
                                    for r in reasoning
                                    if isinstance(r, dict) and r.get("agent") == agent
                                ),
                                None,
                            )
                            rationale = (
                                str(agent_reason.get("rationale"))
                                if agent_reason
                                else "LLM chose this model."
                            )
                            final_reasoning.append(
                                {"agent": agent, "model": assigned_model, "rationale": rationale}
                            )
                        else:
                            final_assignments[agent] = alice_model
                            final_reasoning.append(
                                {
                                    "agent": agent,
                                    "model": alice_model,
                                    "rationale": f"LLM assigned invalid model '{assigned_model}'. Fallback to {alice_model}.",
                                }
                            )

                    return final_assignments, final_reasoning
            else:
                logger.warning("LLM response did not contain JSON block.")
                error_msg = "No JSON found in LLM response."
        except LLMRateLimitError as e:
            # Surface the provider's rate-limit / quota / billing message verbatim
            # so the user knows to upgrade their plan or top up credits. These
            # provider messages never contain the api_key (AC2: secret-free).
            raise PipelineError(str(e)) from e
        except (json.JSONDecodeError, KeyError) as e:
            # Expected parsing errors - log technical detail, keep out of user-facing text
            logger.warning("Failed LLM assignment (parsing): %s", e)
            error_msg = type(e).__name__
        except Exception as e:
            # Other unexpected errors - log full detail but fall back to heuristic
            # assignment so the user can still proceed. The raw error is logged
            # and intentionally not surfaced to the user-facing rationale.
            logger.warning("Failed LLM assignment (unexpected): %s", e)
            error_msg = type(e).__name__

        # Fallback assignment: the LLM-driven assignment was unavailable (e.g. the
        # provider has no chat-completions endpoint, or a transient error). Pick a
        # sensible model per agent from the DISCOVERED set so assignments are
        # differentiated and never reference an undiscovered model (AC3). The raw
        # error is logged above and intentionally not surfaced to the user.
        logger.info("Applying fallback model assignment (reason: %s)", error_msg)
        model_ids = [str(m["id"]) for m in available_models]

        def _pick(keywords: list[str]) -> str:
            for kw in keywords:
                for mid in model_ids:
                    if kw in mid.lower():
                        return mid
            return alice_model

        # Per-agent capability preferences (ordered keyword hints).
        fallback_models = {
            "Alice": _pick(["claude-3-5-sonnet", "gpt-4o", "pro", "sonnet"]),
            "bob": _pick(["opus", "gpt-4o", "gpt-5", "pro", "vision", "sonnet"]),
            "mary": _pick(["sonnet", "gpt-4", "pro", "flash"]),
            "sarah": _pick(["opus", "coder", "sonnet", "gpt-4", "pro"]),
            "jack": _pick(["haiku", "mini", "flash", "lite", "sonnet"]),
        }

        fallback_reasons = {
            "alice": "Chosen for general reasoning and configuration capabilities.",
            "bob": "Chosen for vision-capability, strong reasoning, and long-context processing.",
            "mary": "Chosen for structured output and instruction-following capabilities.",
            "sarah": "Chosen for strong coding and tool execution capabilities.",
            "jack": "Chosen for fast, cost-effective summarization.",
        }

        mappings = {}
        reasoning = []
        for agent in ["bob", "mary", "sarah", "jack"]:
            chosen = fallback_models.get(agent) or alice_model
            mappings[agent] = chosen
            reasoning.append(
                {
                    "agent": agent,
                    "model": chosen,
                    "rationale": fallback_reasons.get(
                        agent, "Chosen based on discovered model capabilities."
                    ),
                }
            )
        return mappings, reasoning

    @staticmethod
    def _mask_endpoint(endpoint: str) -> str:
        """Mask sensitive parts of endpoint for display."""
        if not endpoint:
            return "N/A"

        # Keep domain but mask any API keys in URL
        try:
            from urllib.parse import urlparse

            parsed = urlparse(endpoint)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return endpoint[:30] + "..." if len(endpoint) > 30 else endpoint

    def _format_review_content(self, result: StageResult) -> str:
        """Format review content with model assignments table."""
        if not result.data or "model_assignments" not in result.data:
            return "Review ready."

        assignments: list[dict[str, str]] = result.data.get("model_assignments", [])
        endpoint: str = result.data.get("provider_endpoint", "N/A")
        provider_id = self._selected_provider
        provider_info = self._get_provider_info(provider_id) if provider_id else None
        provider_name = provider_info["name"] if provider_info else "Provider"

        lines = [
            f"Connected successfully to {provider_name}.",
            "",
            "## AI Provider Configuration Review",
            "",
            f"**Provider Endpoint:** {endpoint}",
            "",
            "### Model Assignments",
            "",
            "| Agent | Model | Purpose | Rationale |",
            "|-------|-------|---------|-----------|",
        ]

        for assignment in assignments:
            rationale = assignment.get("rationale", "")
            lines.append(
                f"| {assignment['agent']} | {assignment['model']} | {assignment['purpose']} | {rationale} |"
            )

        lines.extend(
            [
                "",
                "Please review the configuration above. Click **Approve** to save and continue, "
                "or **Reject** to change your provider settings.",
            ]
        )

        return "\n".join(lines)

    def _format_model_assignments(self, config: AliceConfiguration) -> str:
        """Format model assignments from existing config."""
        assignments = self._get_model_assignments_from_config(config, self._model_reasoning)
        endpoint = self._mask_endpoint(config.provider.endpoint)

        lines = [
            "## AI Provider Configuration Review",
            "",
            f"**Provider:** {config.provider.provider_name}",
            f"**Endpoint:** {endpoint}",
            "",
            "### Model Assignments",
            "",
            "| Agent | Model | Purpose | Rationale |",
            "|-------|-------|---------|-----------|",
        ]

        for assignment in assignments:
            rationale = assignment.get("rationale", "")
            lines.append(
                f"| {assignment['agent']} | {assignment['model']} | {assignment['purpose']} | {rationale} |"
            )

        lines.extend(
            [
                "",
                "This is your saved configuration. Click **Approve** to continue with these settings, "
                "or **Reject** to reconfigure.",
            ]
        )

        return "\n".join(lines)
