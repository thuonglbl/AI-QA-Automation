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
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

# Third party
import httpx

# Local
from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.config import AppSettings
from ai_qa.exceptions import PipelineError
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
        "description": "Highest quality · Cloud servers · Personal API key required",
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
        "name": "Claude (Anthropic)",
        "description": "Second highest quality · Enterprise license · API key or SSO login",
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
        "id": "gemini-chatgpt",
        "name": "Gemini / ChatGPT",
        "description": "Good quality · Cloud · Personal API key from Google or OpenAI",
        "quality_rank": 3,
        "security_level": "cloud",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your Gemini or OpenAI API key...",
            }
        ],
        "endpoint_setting": "openai_api_base_url",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "on-premises",
        "name": "On-Premises",
        "description": "Highest security · All data stays on your infrastructure · Company API key",
        "quality_rank": 4,
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
    "bob": "Requirements extraction from Confluence (requires vision-capable model for image captioning)",
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
        self._settings = AppSettings()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def check_existing_configuration(self) -> AliceConfiguration | None:
        """Check for existing valid configuration in DB.

        Returns:
            AliceConfiguration if valid config exists, None otherwise
        """
        if not self.project_context or not self.project_context.artifact_service:
            return None

        db = self.project_context.artifact_service.db
        from ai_qa.db.models import User

        user = db.get(User, self.project_context.user_id)

        if not user or not user.ai_provider_config or not user.ai_agents_config:
            return None

        try:
            if not self._is_config_valid(user.ai_provider_config):
                logger.info("Existing configuration expired or invalid")
                return None

            provider_config = ProviderConfig.model_validate(user.ai_provider_config)
            agents_config = AgentsConfig.model_validate(user.ai_agents_config)

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

    def get_on_prem_defaults(self) -> dict[str, str]:
        """Get On-Premises default values from .env.

        Returns:
            Dict with server_url and api_key from user config or settings
        """
        # Use per-user config if available, otherwise empty (user must configure via Alice UI)
        if self.project_context and self.project_context.artifact_service:
            db = self.project_context.artifact_service.db
            from ai_qa.db.models import User

            user = db.get(User, self.project_context.user_id)
            if user and user.settings:
                return {
                    "server_url": str(user.settings.get("on_premises_ai_server_url", "")),
                    "api_key": str(user.settings.get("on_premises_ai_server_key", "")),
                }
        return {"server_url": "", "api_key": ""}

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

        # Test connection
        await self._send_connection_test_status(
            "testing", f"Testing connection to {provider_info['name']}..."
        )

        try:
            connection_success = await self._test_connection(provider_info, credentials)
        except Exception as exc:
            logger.error("Connection test failed: %s", exc)
            connection_success = False

        if not connection_success:
            await self._send_connection_test_status(
                "failed", f"Connection to {provider_info['name']} failed"
            )
            raise PipelineError(
                f"Failed to connect to {provider_info['name']}. "
                "Please check your credentials and try again."
            )

        # Persist credentials if user is authenticated
        if self.project_context and self.project_context.artifact_service:
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.db.models import User

                user = db.get(User, self.project_context.user_id)
                if user:
                    # SQLAlchemy requires re-assignment or flag_modified for JSON mutation to be tracked
                    settings = user.settings.copy() if user.settings else {}
                    api_key = credentials.get("api_key", "")
                    if provider_info["id"] == "on-premises":
                        settings["on_premises_ai_server_key"] = api_key
                    elif provider_info["id"] == "claude":
                        settings["anthropic_api_key"] = api_key
                    elif provider_info["id"] == "gemini-chatgpt":
                        settings["openai_api_key"] = api_key
                    elif provider_info["id"] == "browser-use-cloud":
                        settings["browser_use_api_key"] = api_key

                    user.settings = settings
                    db.commit()
            except Exception as e:
                logger.warning(f"Failed to persist user credentials: {e}")

        # Generate configuration
        self._configuration = await self._generate_configuration(provider_info, credentials)

        # Return result with model assignments for review
        return StageResult(
            success=True,
            data={
                "configuration": self._configuration.model_dump(),
                "model_assignments": self._get_model_assignments_display(),
                "provider_endpoint": self._mask_endpoint(self._configuration.provider.endpoint),
            },
        )

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override handle_start to support existing configuration check."""
        # Check for existing configuration first
        existing_config = await self.check_existing_configuration()

        if existing_config and not input_data.get("force_reconfigure"):
            # Use existing configuration
            self._configuration = existing_config
            self._selected_provider = existing_config.provider.provider

            # Show review with existing config
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content=self._format_model_assignments(existing_config),
                message_type="text",
                metadata={
                    "configuration": existing_config.model_dump(),
                    "model_assignments": self._get_model_assignments_from_config(existing_config),
                    "provider_endpoint": self._mask_endpoint(existing_config.provider.endpoint),
                },
            )
            return

        # Check if user already selected provider (frontend sent provider in input_data)
        if input_data.get("provider"):
            # User already selected provider, skip greeting and go straight to processing
            await self.transition_to(AgentState.PROCESSING)
            try:
                result = await self.process(input_data, feedback=None)
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

        await self.transition_to(AgentState.DONE)

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _get_provider_info(self, provider_id: str) -> dict[str, Any] | None:
        """Get provider info by ID."""
        for p in PROVIDER_OPTIONS:
            if p["id"] == provider_id:
                info = p.copy()
                setting_name = info.get("endpoint_setting")
                if setting_name:
                    info["endpoint"] = getattr(self._settings, setting_name, "")
                return info
        return None

    async def _test_connection(
        self, provider_info: dict[str, Any], credentials: dict[str, str]
    ) -> bool:
        """Test connection to provider.

        Args:
            provider_info: Provider configuration
            credentials: User-provided credentials

        Returns:
            True if connection successful, False otherwise
        """
        # Real connection test
        endpoint = provider_info.get("endpoint", "")
        if provider_info["id"] == "on-premises":
            if not endpoint or not endpoint.startswith("http"):
                return False

        api_key = credentials.get("api_key", "").strip()
        if not api_key or len(api_key) < 8:
            return False

        available_models = await self._fetch_available_models(
            provider_info["id"], endpoint, api_key
        )
        if not available_models:
            return False

        logger.info("Connection test passed for %s", provider_info["name"])
        return True

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

        # 1. Fetch available models
        available_models = await self._fetch_available_models(provider_id, endpoint, api_key)

        if not available_models:
            raise PipelineError(
                "No models discovered from provider. Please check the provider configuration."
            )

        # 2. Bootstrap Alice model
        alice_model = self._bootstrap_alice_model(available_models)
        if not alice_model:
            raise PipelineError(
                "Could not bootstrap a reasoning model for Alice from the available models."
            )

        # 3. Assign models via LLM
        model_mappings, reasoning = await self._assign_models_via_llm(
            provider_id, endpoint, api_key, alice_model, available_models
        )

        # 4. Emit thinking trace
        trace_payload = {
            "connection_status": "success",
            "available_models": available_models,
            "bootstrap_model": alice_model,
            "agent_needs": AGENT_PURPOSES,
            "assignments": reasoning,
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
            credential_reference=f"env://{provider_info['env_key']}",
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

        return AliceConfiguration(provider=provider_config, agents=agents_config)

    def _save_configuration(self, config: AliceConfiguration) -> None:
        """Save configuration to User database."""
        if not self.project_context or not self.project_context.artifact_service:
            logger.error("No project context available to save configuration.")
            raise OSError("No project context available to save configuration.")

        db = self.project_context.artifact_service.db
        from ai_qa.db.models import User

        user = db.get(User, self.project_context.user_id)

        if user:
            user.ai_provider_config = config.provider.model_dump()
            user.ai_agents_config = config.agents.model_dump()
            db.commit()
            logger.info("Configuration saved to database for user %s", user.email)
        else:
            raise OSError("User not found to save configuration.")

    def _is_config_valid(self, provider_data: dict[str, Any]) -> bool:
        """Check if existing configuration is still valid (not expired)."""
        try:
            tested_at = datetime.fromisoformat(provider_data.get("tested_at", "1970-01-01"))
            age_days = (datetime.now(UTC) - tested_at).days
            return age_days < 30
        except (ValueError, TypeError):
            return False

    def _get_model_assignments_display(self) -> list[dict[str, str]]:
        """Get model assignments for display in review."""
        if not self._configuration:
            return []

        return self._get_model_assignments_from_config(self._configuration)

    def _get_model_assignments_from_config(
        self, config: AliceConfiguration
    ) -> list[dict[str, str]]:
        """Get model assignments from configuration."""
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
                }
            )
        return assignments

    def _bootstrap_alice_model(self, available_models: list[dict[str, Any]]) -> str:
        """Bootstrap Alice's reasoning model using keyword heuristics."""
        if not available_models:
            return ""

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
                    return str(m_id)

        # Fallback to first available
        return str(model_ids[0])

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
                error_msg = f"No JSON found. Response: {response_text[:200]}"
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.warning(f"Failed LLM assignment: {e}")
            error_msg = f"Exception: {str(e)}"
            if "response_text" in locals():
                error_msg += f" | Response: {response_text[:200]}"

        # Fallback mapping
        mappings = {}
        reasoning = []
        for agent in ["bob", "mary", "sarah", "jack"]:
            mappings[agent] = alice_model
            reasoning.append(
                {
                    "agent": agent,
                    "model": alice_model,
                    "rationale": f"Fallback heuristic applied: {error_msg}",
                }
            )
        return mappings, reasoning

    def _mask_endpoint(self, endpoint: str) -> str:
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
            "| Agent | Model | Purpose |",
            "|-------|-------|---------|",
        ]

        for assignment in assignments:
            lines.append(
                f"| {assignment['agent']} | {assignment['model']} | {assignment['purpose']} |"
            )

        lines.extend(
            [
                "",
                "Please review the configuration above. Click **Approve** to save and continue, "
                "or **Reject** to change your provider settings.",
            ]
        )

        return "\n".join(lines)

    async def _fetch_available_models(
        self, provider_id: str, server_url: str, api_key: str
    ) -> list[dict[str, Any]]:
        """Fetch available models from on-premise LLM server or return known models for cloud.

        Tries common endpoints: /v1/models, /models, /api/models, /api/tags (Ollama)
        """
        if provider_id == "claude":
            return [
                {"id": "claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet"},
                {"id": "claude-3-opus-latest", "name": "Claude 3 Opus"},
                {"id": "claude-3-5-haiku-latest", "name": "Claude 3.5 Haiku"},
            ]
        elif provider_id == "gemini-chatgpt":
            return [
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
                {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
                {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash"},
            ]
        elif provider_id == "browser-use-cloud":
            return [
                {"id": "gpt-4o", "name": "GPT-4o"},
                {"id": "claude-3-5-sonnet-latest", "name": "Claude 3.5 Sonnet"},
            ]

        endpoints_to_try = [
            f"{server_url.rstrip('/')}/v1/models",
            f"{server_url.rstrip('/')}/models",
            f"{server_url.rstrip('/')}/api/tags",  # Ollama
            f"{server_url.rstrip('/')}/api/models",
        ]

        headers = {"Authorization": f"Bearer {api_key}"}
        verify_ssl = provider_id != "on-premises"

        for endpoint in endpoints_to_try:
            try:
                # Use verify_ssl to support self-signed certificates common in on-premise setups
                async with httpx.AsyncClient(
                    timeout=10.0, verify=verify_ssl, follow_redirects=True
                ) as client:
                    response = await client.get(endpoint, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        # Handle different response formats
                        if isinstance(data, list):
                            return [
                                {
                                    "id": m.get("id", m.get("name", str(m))),
                                    "name": m.get("name", m.get("id", str(m))),
                                }
                                for m in data
                                if isinstance(m, dict)
                            ]
                        elif isinstance(data, dict) and "data" in data:
                            return [
                                {
                                    "id": m.get("id", m.get("name", str(m))),
                                    "name": m.get("name", m.get("id", str(m))),
                                }
                                for m in data["data"]
                                if isinstance(m, dict)
                            ]
                        elif isinstance(data, dict) and "models" in data:
                            # Ollama /api/tags uses 'models' with 'name'
                            return [
                                {
                                    "id": m.get("id", m.get("name", str(m))),
                                    "name": m.get("name", m.get("id", str(m))),
                                }
                                for m in data["models"]
                                if isinstance(m, dict)
                            ]
            except Exception as exc:
                logger.debug("Failed to fetch models from %s: %s", endpoint, exc)
                continue

        return []

    def _format_model_assignments(self, config: AliceConfiguration) -> str:
        """Format model assignments from existing config."""
        assignments = self._get_model_assignments_from_config(config)
        endpoint = self._mask_endpoint(config.provider.endpoint)

        lines = [
            "## AI Provider Configuration Review",
            "",
            f"**Provider:** {config.provider.provider_name}",
            f"**Endpoint:** {endpoint}",
            "",
            "### Model Assignments",
            "",
            "| Agent | Model | Purpose |",
            "|-------|-------|---------|",
        ]

        for assignment in assignments:
            lines.append(
                f"| {assignment['agent']} | {assignment['model']} | {assignment['purpose']} |"
            )

        lines.extend(
            [
                "",
                "This is your saved configuration. Click **Approve** to continue with these settings, "
                "or **Reject** to reconfigure.",
            ]
        )

        return "\n".join(lines)
