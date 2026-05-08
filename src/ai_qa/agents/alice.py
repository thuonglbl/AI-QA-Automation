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
from datetime import UTC, datetime
from pathlib import Path
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
        "quality_rank": 1,
        "security_level": "cloud",
        "credential_fields": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True}
        ],
        "endpoint": "https://api.browser-use.com",
        "env_key": "BROWSER_USE_API_KEY",
    },
    {
        "id": "claude",
        "name": "Claude (Anthropic)",
        "quality_rank": 2,
        "security_level": "enterprise",
        "credential_fields": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True}
        ],
        "endpoint": "https://api.anthropic.com",
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "gemini-chatgpt",
        "name": "Gemini / ChatGPT",
        "quality_rank": 3,
        "security_level": "cloud",
        "credential_fields": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True}
        ],
        "endpoint": "https://api.openai.com",
        "env_key": "OPENAI_API_KEY",
    },
    {
        "id": "on-premises",
        "name": "On-Premises LLM",
        "quality_rank": 4,
        "security_level": "highest",
        "credential_fields": [
            {
                "name": "server_url",
                "label": "Server URL",
                "type": "url",
                "required": True,
                "placeholder": "https://ai-server.company.com",
            },
            {"name": "api_key", "label": "API Key", "type": "password", "required": True},
        ],
        "endpoint": "",  # User-provided
        "env_key": "ON_PREMISES_AI_SERVER_KEY",
    },
]

# Default model mappings per provider
DEFAULT_MODEL_MAPPINGS: dict[str, dict[str, str]] = {
    "claude": {
        "bob": "claude-3-opus-20240229",
        "mary": "claude-3-sonnet-20240229",
        "sarah": "claude-3-sonnet-20240229",
        "jack": "claude-3-haiku-20240307",
    },
    "on-premises": {
        "bob": "deepseek-coder-33b",
        "mary": "qwen-72b-chat",
        "sarah": "qwen-72b-chat",
        "jack": "qwen-7b-chat",
    },
    "browser-use-cloud": {
        "bob": "gpt-4",
        "mary": "gpt-4",
        "sarah": "gpt-4",
        "jack": "gpt-3.5-turbo",
    },
    "gemini-chatgpt": {
        "bob": "gemini-pro",
        "mary": "gemini-pro",
        "sarah": "gemini-pro",
        "jack": "gemini-flash",
    },
}

# Agent purposes for display
AGENT_PURPOSES: dict[str, str] = {
    "bob": "Requirements extraction from Confluence",
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

    def __init__(self, workspace_dir: Path | None = None) -> None:
        """Initialize Alice Agent.

        Args:
            workspace_dir: Override workspace directory path (for testing)
        """
        super().__init__(
            name="Alice",
            color="#EC4899",  # Pink per UX-DR19
            step_number=1,
            step_title="AI Provider Configuration",
            workspace_dir=workspace_dir,
        )
        self._selected_provider: str | None = None
        self._provider_credentials: dict[str, str] = {}
        self._configuration: AliceConfiguration | None = None
        self._settings = AppSettings()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def check_existing_configuration(self) -> AliceConfiguration | None:
        """Check for existing valid configuration.

        Returns:
            AliceConfiguration if valid config exists, None otherwise
        """
        provider_path = self._workspace_dir / "configuration" / "provider.json"
        agents_path = self._workspace_dir / "configuration" / "agents.json"

        if not provider_path.exists() or not agents_path.exists():
            return None

        try:
            provider_data = json.loads(provider_path.read_text())
            agents_data = json.loads(agents_path.read_text())

            # Validate configuration is not expired (30 days)
            if not self._is_config_valid(provider_data):
                logger.info("Existing configuration expired or invalid")
                return None

            provider_config = ProviderConfig(**provider_data)
            agents_config = AgentsConfig(**agents_data)

            return AliceConfiguration(provider=provider_config, agents=agents_config)

        except (json.JSONDecodeError, OSError, ValueError) as exc:
            logger.warning("Failed to load existing configuration: %s", exc)
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
        if self._user_email:
            from ai_qa.config import UserConfig

            user_config = UserConfig.load(self._user_email)
            return {
                "server_url": user_config.on_premises_ai_server_url or "",
                "api_key": user_config.on_premises_ai_server_key or "",
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

        await self._send_connection_test_status(
            "success", f"Successfully connected to {provider_info['name']}"
        )

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

            await self.send_message(
                content=(
                    f"Welcome back! I'm Alice. Using your saved {existing_config.provider.provider_name} "
                    f"configuration from {existing_config.provider.tested_at[:10]}.\n\n"
                    f"You can reconfigure by selecting 'Change Provider' at any time."
                ),
                message_type="info",
                metadata={"has_existing_config": True},
            )

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

    async def handle_approve(self) -> None:
        """Save configuration and complete Alice step."""
        if self._configuration is None:
            logger.error("Cannot approve - no configuration generated")
            await self.send_message(
                content="Error: No configuration to approve. Please start over.",
                message_type="error",
            )
            return

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

        await super().handle_approve()

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _get_provider_info(self, provider_id: str) -> dict[str, Any] | None:
        """Get provider info by ID."""
        for p in PROVIDER_OPTIONS:
            if p["id"] == provider_id:
                return p
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
        # Simulate connection test for now
        # In production, this would make actual API calls
        await self._simulate_delay(1.0)

        # Basic validation
        if provider_info["id"] == "on-premises":
            server_url = credentials.get("server_url", "").strip()
            if not server_url or not server_url.startswith("http"):
                return False

        api_key = credentials.get("api_key", "").strip()
        if not api_key or len(api_key) < 8:
            return False

        # TODO: Implement actual API connection test in Epic 4-1 (LLM abstraction layer)
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
        if provider_id == "on-premises":
            endpoint = credentials.get("server_url", "").rstrip("/")
        else:
            endpoint = provider_info["endpoint"]

        # Create provider config
        provider_config = ProviderConfig(
            provider=provider_id,
            provider_name=provider_info["name"],
            endpoint=endpoint,
            credential_reference=f"env://{provider_info['env_key']}",
            tested_at=now,
            test_result="success",
        )

        # Create agents config with model assignments
        # For on-premise, discover and smart-match models
        if provider_id == "on-premises":
            server_url = credentials.get("server_url", "")
            api_key = credentials.get("api_key", "")
            available_models = await self._fetch_available_models(server_url, api_key)
            if available_models:
                model_mappings = self._match_models_to_agents(available_models)
                logger.info("Using discovered models: %s", model_mappings)
            else:
                model_mappings = DEFAULT_MODEL_MAPPINGS.get(
                    "on-premises", DEFAULT_MODEL_MAPPINGS["claude"]
                )
                logger.warning("Could not discover models, using defaults: %s", model_mappings)
        else:
            model_mappings = DEFAULT_MODEL_MAPPINGS.get(
                provider_id, DEFAULT_MODEL_MAPPINGS["claude"]
            )

        agents: dict[str, AgentModelConfig] = {}
        for agent_name in ["bob", "mary", "sarah", "jack"]:
            agents[agent_name] = AgentModelConfig(
                model=model_mappings.get(agent_name, "claude-3-sonnet-20240229"),
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
        """Save configuration to workspace files.

        Args:
            config: Complete AliceConfiguration to save

        Raises:
            OSError: If file writing fails
        """
        config_dir = self._workspace_dir / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)

        provider_path = config_dir / "provider.json"
        agents_path = config_dir / "agents.json"

        provider_path.write_text(
            json.dumps(config.provider.model_dump(), indent=2),
            encoding="utf-8",
        )
        agents_path.write_text(
            json.dumps(config.agents.model_dump(), indent=2),
            encoding="utf-8",
        )

        logger.info("Configuration saved to %s", config_dir)

    def _is_config_valid(self, provider_data: dict[str, Any]) -> bool:
        """Check if existing configuration is still valid (not expired).

        Args:
            provider_data: Provider configuration data

        Returns:
            True if config is valid (tested within 30 days)
        """
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

        lines = [
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

    async def _fetch_available_models(self, server_url: str, api_key: str) -> list[dict[str, Any]]:
        """Fetch available models from on-premise LLM server.

        Tries common endpoints: /v1/models, /models, /api/models
        """
        endpoints_to_try = [
            f"{server_url.rstrip('/')}/v1/models",
            f"{server_url.rstrip('/')}/models",
            f"{server_url.rstrip('/')}/api/models",
        ]

        headers = {"Authorization": f"Bearer {api_key}"}

        for endpoint in endpoints_to_try:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(endpoint, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        # Handle different response formats
                        if isinstance(data, list):
                            return [
                                {"id": m.get("id", m), "name": m.get("id", str(m))} for m in data
                            ]
                        elif isinstance(data, dict) and "data" in data:
                            return [
                                {"id": m.get("id", m), "name": m.get("id", str(m))}
                                for m in data["data"]
                            ]
                        elif isinstance(data, dict) and "models" in data:
                            return [
                                {"id": m.get("id", m), "name": m.get("id", str(m))}
                                for m in data["models"]
                            ]
            except Exception as exc:
                logger.debug("Failed to fetch models from %s: %s", endpoint, exc)
                continue

        return []

    def _match_models_to_agents(self, available_models: list[dict[str, Any]]) -> dict[str, str]:
        """Smart match available models to agents based on capabilities.

        Priority:
        1. Bob (requirements): Best code/understanding model (coder, large, reasoning)
        2. Mary (test cases): Balanced model (general purpose, medium)
        3. Sarah (scripts): Coding + browser automation capable
        4. Jack (execution): Fast/light model (small, fast)
        """
        if not available_models:
            # Fallback to hardcoded defaults
            return DEFAULT_MODEL_MAPPINGS.get("on-premises", {})

        def score_model_for_agent(model_id: str, agent: str) -> int:
            """Score how well a model fits an agent's needs."""
            score = 0
            model_lower = model_id.lower()

            # Size indicators
            has_large = any(
                x in model_lower for x in ["70b", "72b", "33b", "65b", "40b", "large", "xl"]
            )
            has_medium = any(x in model_lower for x in ["13b", "14b", "20b", "medium"])
            has_small = any(x in model_lower for x in ["7b", "8b", "9b", "small", "mini", "tiny"])

            # Capability indicators
            is_coder = any(x in model_lower for x in ["code", "coder", "deepseek", "qwen-coder"])
            is_reasoning = any(x in model_lower for x in ["reasoning", "o1", "r1", "qwq"])
            is_chat = any(x in model_lower for x in ["chat", "instruct"])

            if agent == "bob":
                # Bob needs best understanding for requirements
                if is_coder:
                    score += 10
                if is_reasoning:
                    score += 8
                if has_large:
                    score += 5
                if has_medium:
                    score += 3

            elif agent == "mary":
                # Mary needs balanced general purpose
                if is_chat:
                    score += 5
                if has_large:
                    score += 4
                if has_medium:
                    score += 6  # Prefer medium for cost/speed balance

            elif agent == "sarah":
                # Sarah needs coding for test scripts
                if is_coder:
                    score += 10
                if has_large:
                    score += 4
                if has_medium:
                    score += 3

            elif agent == "jack":
                # Jack needs fast execution
                if has_small:
                    score += 10
                elif has_medium:
                    score += 5
                if is_chat and not is_coder:
                    score += 3

            # Penalize if clearly wrong type
            if agent in ["bob", "sarah"] and not is_coder and not is_chat:
                score -= 3

            return score

        assignments = {}
        for agent in ["bob", "mary", "sarah", "jack"]:
            best_model = None
            best_score = -1

            for model in available_models:
                model_id = model.get("id", "")
                score = score_model_for_agent(model_id, agent)
                if score > best_score:
                    best_score = score
                    best_model = model_id

            if best_model:
                assignments[agent] = best_model
            else:
                # Fallback to default
                assignments[agent] = DEFAULT_MODEL_MAPPINGS.get("on-premises", {}).get(
                    agent, "unknown"
                )

        logger.info("Smart model matching: %s", assignments)
        return assignments

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
