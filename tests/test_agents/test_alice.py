"""Tests for Alice Agent — AI Provider Selection & Configuration.

Tests cover:
- Agent initialization and greeting
- Provider selection workflow
- Connection testing (with mocked LLM client)
- Configuration file writing
- Existing configuration loading
- Model assignment generation
"""

# Standard library
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Local
from ai_qa.agents.alice import DEFAULT_MODEL_MAPPINGS, PROVIDER_OPTIONS, AliceAgent
from ai_qa.agents.base import AgentState
from ai_qa.exceptions import PipelineError
from ai_qa.models import AliceConfiguration


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    """Create a temporary workspace directory."""
    return tmp_path


@pytest.fixture
def alice(temp_workspace: Path) -> AliceAgent:
    """Create an AliceAgent with temp workspace."""
    return AliceAgent(workspace_dir=temp_workspace)


class TestAliceInitialization:
    """Test Alice agent initialization (AC: 1)."""

    def test_agent_properties(self, alice: AliceAgent) -> None:
        """Alice has correct name, color, step number, and title."""
        assert alice.name == "Alice"
        assert alice.color == "#EC4899"  # Pink per UX-DR19
        assert alice.step_number == 1
        assert alice.step_title == "AI Provider Configuration"

    def test_initial_state(self, alice: AliceAgent) -> None:
        """Alice starts in START state."""
        assert alice.state == AgentState.START

    def test_workspace_created(self, temp_workspace: Path, alice: AliceAgent) -> None:
        """Workspace directories are created on init."""
        assert (temp_workspace / "configuration").exists()


class TestProviderOptions:
    """Test provider options API (AC: 2)."""

    def test_get_provider_options_structure(self, alice: AliceAgent) -> None:
        """Provider options have correct structure with 4 options."""
        options = alice.get_provider_options()

        assert len(options) == 4

        # Check all expected providers present
        provider_ids = [p["id"] for p in options]
        assert "browser-use-cloud" in provider_ids
        assert "claude" in provider_ids
        assert "gemini-chatgpt" in provider_ids
        assert "on-premises" in provider_ids

    def test_provider_quality_ranks(self, alice: AliceAgent) -> None:
        """Providers have correct quality ranks."""
        options = alice.get_provider_options()

        by_id = {p["id"]: p for p in options}

        assert by_id["browser-use-cloud"]["quality_rank"] == 1
        assert by_id["claude"]["quality_rank"] == 2
        assert by_id["gemini-chatgpt"]["quality_rank"] == 3
        assert by_id["on-premises"]["quality_rank"] == 4

    def test_provider_security_levels(self, alice: AliceAgent) -> None:
        """Providers have correct security levels."""
        options = alice.get_provider_options()

        by_id = {p["id"]: p for p in options}

        assert by_id["browser-use-cloud"]["security_level"] == "cloud"
        assert by_id["claude"]["security_level"] == "enterprise"
        assert by_id["gemini-chatgpt"]["security_level"] == "cloud"
        assert by_id["on-premises"]["security_level"] == "highest"

    def test_credential_fields(self, alice: AliceAgent) -> None:
        """Providers have appropriate credential fields."""
        options = alice.get_provider_options()

        by_id = {p["id"]: p for p in options}

        # Cloud providers need only API key
        for provider_id in ["browser-use-cloud", "claude", "gemini-chatgpt"]:
            fields = by_id[provider_id]["credential_fields"]
            assert len(fields) == 1
            assert fields[0]["name"] == "api_key"
            assert fields[0]["type"] == "password"

        # On-premises needs server_url + api_key
        on_prem = by_id["on-premises"]
        assert len(on_prem["credential_fields"]) == 2
        assert on_prem["credential_fields"][0]["name"] == "server_url"
        assert on_prem["credential_fields"][0]["type"] == "url"
        assert on_prem["credential_fields"][1]["name"] == "api_key"


class TestOnPremDefaults:
    """Test On-Premises credential pre-fill (AC: 9)."""

    def test_get_on_prem_defaults_empty(self, alice: AliceAgent) -> None:
        """Returns empty strings when no env vars set."""
        defaults = alice.get_on_prem_defaults()

        assert "server_url" in defaults
        assert "api_key" in defaults


class TestProcessWorkflow:
    """Test Alice process workflow (AC: 3, 4, 5)."""

    @pytest.mark.asyncio
    async def test_process_valid_claude_credentials(self, alice: AliceAgent) -> None:
        """Process succeeds with valid Claude credentials."""
        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }

        result = await alice.process(input_data, feedback=None)

        assert result.success is True
        assert result.data is not None
        assert "configuration" in result.data
        assert "model_assignments" in result.data

    @pytest.mark.asyncio
    async def test_process_valid_on_prem_credentials(self, alice: AliceAgent) -> None:
        """Process succeeds with valid On-Premises credentials."""
        input_data = {
            "provider": "on-premises",
            "credentials": {
                "server_url": "https://ai-server.company.com",
                "api_key": "test-api-key-12345",
            },
        }

        result = await alice.process(input_data, feedback=None)

        assert result.success is True
        assert result.data is not None
        assert (
            result.data["configuration"]["provider"]["endpoint"] == "https://ai-server.company.com"
        )

    @pytest.mark.asyncio
    async def test_process_missing_provider(self, alice: AliceAgent) -> None:
        """Process raises PipelineError when provider not selected."""
        input_data = {"credentials": {"api_key": "test"}}

        with pytest.raises(PipelineError, match="No provider selected"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    async def test_process_invalid_provider(self, alice: AliceAgent) -> None:
        """Process raises PipelineError for unknown provider."""
        input_data = {"provider": "invalid-provider", "credentials": {"api_key": "test"}}

        with pytest.raises(PipelineError, match="Unknown provider"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    async def test_process_missing_api_key(self, alice: AliceAgent) -> None:
        """Process fails with missing/short API key."""
        input_data = {"provider": "claude", "credentials": {"api_key": "short"}}

        with pytest.raises(PipelineError, match="Failed to connect"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    async def test_process_invalid_server_url(self, alice: AliceAgent) -> None:
        """Process fails with invalid server URL for on-premises."""
        input_data = {
            "provider": "on-premises",
            "credentials": {
                "server_url": "not-a-valid-url",
                "api_key": "valid-api-key-12345",
            },
        }

        with pytest.raises(PipelineError, match="Failed to connect"):
            await alice.process(input_data, feedback=None)

    @pytest.mark.asyncio
    async def test_process_with_feedback(self, alice: AliceAgent) -> None:
        """Process handles feedback/rejection correctly."""
        result = await alice.process(input_data={}, feedback="Change provider")

        assert result.success is True
        assert result.data["action"] == "restart_selection"


class TestModelAssignments:
    """Test model assignment generation (AC: 5)."""

    @pytest.mark.asyncio
    async def test_claude_model_assignments(self, alice: AliceAgent) -> None:
        """Claude provider assigns correct models to agents."""
        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }

        result = await alice.process(input_data)

        config = result.data["configuration"]
        agents = config["agents"]["agents"]

        assert agents["bob"]["model"] == "claude-3-opus-20240229"
        assert agents["mary"]["model"] == "claude-3-sonnet-20240229"
        assert agents["sarah"]["model"] == "claude-3-sonnet-20240229"
        assert agents["jack"]["model"] == "claude-3-haiku-20240307"

    @pytest.mark.asyncio
    async def test_on_prem_model_assignments(self, alice: AliceAgent) -> None:
        """On-premises provider assigns correct models to agents."""
        input_data = {
            "provider": "on-premises",
            "credentials": {
                "server_url": "https://ai-server.company.com",
                "api_key": "test-api-key-12345",
            },
        }

        result = await alice.process(input_data)

        config = result.data["configuration"]
        agents = config["agents"]["agents"]

        assert agents["bob"]["model"] == "deepseek-coder-33b"
        assert agents["mary"]["model"] == "qwen-72b-chat"
        assert agents["sarah"]["model"] == "qwen-72b-chat"
        assert agents["jack"]["model"] == "qwen-7b-chat"

    @pytest.mark.asyncio
    async def test_model_assignments_have_tools(self, alice: AliceAgent) -> None:
        """Model assignments include correct tools for each agent."""
        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }

        result = await alice.process(input_data)

        config = result.data["configuration"]
        agents = config["agents"]["agents"]

        assert "confluence_reader" in agents["bob"]["tools"]
        assert "test_case_extractor" in agents["mary"]["tools"]
        assert "script_generator" in agents["sarah"]["tools"]
        assert "script_runner" in agents["jack"]["tools"]

    @pytest.mark.asyncio
    async def test_model_assignments_have_prompt_templates(self, alice: AliceAgent) -> None:
        """Model assignments include prompt templates."""
        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }

        result = await alice.process(input_data)

        config = result.data["configuration"]
        agents = config["agents"]["agents"]

        assert agents["bob"]["prompt_template"] == "test_extraction_v1"
        assert agents["mary"]["prompt_template"] == "test_case_generation_v1"


class TestConfigurationPersistence:
    """Test configuration file persistence (AC: 7, 8)."""

    @pytest.mark.asyncio
    async def test_configuration_saved_to_files(
        self, temp_workspace: Path, alice: AliceAgent
    ) -> None:
        """Configuration is saved to provider.json and agents.json."""
        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }

        # Process to generate configuration
        result = await alice.process(input_data)
        assert result.success

        # Save configuration
        config = AliceConfiguration(**result.data["configuration"])
        alice._save_configuration(config)

        # Verify files exist
        provider_path = temp_workspace / "configuration" / "provider.json"
        agents_path = temp_workspace / "configuration" / "agents.json"

        assert provider_path.exists()
        assert agents_path.exists()

        # Verify content
        provider_data = json.loads(provider_path.read_text())
        assert provider_data["provider"] == "claude"
        assert provider_data["provider_name"] == "Claude (Anthropic)"
        assert provider_data["test_result"] == "success"

        agents_data = json.loads(agents_path.read_text())
        assert agents_data["version"] == "1.0"
        assert "agents" in agents_data
        assert "bob" in agents_data["agents"]


class TestExistingConfiguration:
    """Test existing configuration loading (AC: 8)."""

    @pytest.mark.asyncio
    async def test_check_existing_configuration_valid(
        self, temp_workspace: Path, alice: AliceAgent
    ) -> None:
        """Valid existing configuration is loaded."""
        # Create valid configuration files
        config_dir = temp_workspace / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(UTC).isoformat()

        provider_data = {
            "provider": "claude",
            "provider_name": "Claude (Anthropic)",
            "endpoint": "https://api.anthropic.com",
            "credential_reference": "env://ANTHROPIC_API_KEY",
            "tested_at": now,
            "test_result": "success",
        }

        agents_data = {
            "version": "1.0",
            "updated_at": now,
            "agents": {
                "bob": {
                    "model": "claude-3-opus-20240229",
                    "temperature": 0.0,
                    "prompt_template": "test_extraction_v1",
                    "tools": ["confluence_reader"],
                }
            },
        }

        (config_dir / "provider.json").write_text(json.dumps(provider_data))
        (config_dir / "agents.json").write_text(json.dumps(agents_data))

        # Check existing configuration
        existing = await alice.check_existing_configuration()

        assert existing is not None
        assert existing.provider.provider == "claude"
        assert "bob" in existing.agents.agents

    @pytest.mark.asyncio
    async def test_check_existing_configuration_expired(
        self, temp_workspace: Path, alice: AliceAgent
    ) -> None:
        """Expired configuration (30+ days) is rejected."""
        # Create expired configuration
        config_dir = temp_workspace / "configuration"
        config_dir.mkdir(parents=True, exist_ok=True)

        expired_date = (datetime.now(UTC) - timedelta(days=31)).isoformat()

        provider_data = {
            "provider": "claude",
            "provider_name": "Claude (Anthropic)",
            "endpoint": "https://api.anthropic.com",
            "credential_reference": "env://ANTHROPIC_API_KEY",
            "tested_at": expired_date,
            "test_result": "success",
        }

        agents_data = {
            "version": "1.0",
            "updated_at": expired_date,
            "agents": {},
        }

        (config_dir / "provider.json").write_text(json.dumps(provider_data))
        (config_dir / "agents.json").write_text(json.dumps(agents_data))

        # Check expired configuration
        existing = await alice.check_existing_configuration()

        assert existing is None

    @pytest.mark.asyncio
    async def test_check_existing_configuration_missing(
        self, temp_workspace: Path, alice: AliceAgent
    ) -> None:
        """No configuration returns None."""
        existing = await alice.check_existing_configuration()
        assert existing is None


class TestApproveWorkflow:
    """Test approve workflow (AC: 6, 7)."""

    @pytest.mark.asyncio
    async def test_approve_saves_configuration(
        self, temp_workspace: Path, alice: AliceAgent
    ) -> None:
        """Approve saves configuration and transitions to done."""
        # First process to generate configuration
        input_data = {
            "provider": "claude",
            "credentials": {"api_key": "test-api-key-12345"},
        }
        await alice.process(input_data)

        # Approve
        await alice.handle_approve()

        # Verify configuration saved
        provider_path = temp_workspace / "configuration" / "provider.json"
        assert provider_path.exists()

        # Verify state transition
        assert alice.state == AgentState.DONE

    @pytest.mark.asyncio
    async def test_approve_without_configuration_fails(self, alice: AliceAgent) -> None:
        """Approve without configuration sends error message."""
        await alice.handle_approve()

        # State should remain START (not transition to DONE)
        assert alice.state == AgentState.START


class TestDefaultModelMappings:
    """Test default model mappings are defined correctly."""

    def test_all_providers_have_mappings(self) -> None:
        """All provider IDs have default model mappings."""
        provider_ids = [p["id"] for p in PROVIDER_OPTIONS]

        for provider_id in provider_ids:
            assert provider_id in DEFAULT_MODEL_MAPPINGS, f"Missing mappings for {provider_id}"

    def test_all_agents_have_models_per_provider(self) -> None:
        """All 4 agents have model assignments per provider."""
        agent_names = ["bob", "mary", "sarah", "jack"]

        for provider_id, mappings in DEFAULT_MODEL_MAPPINGS.items():
            for agent_name in agent_names:
                assert agent_name in mappings, f"Missing {agent_name} mapping for {provider_id}"
