import json
import os
from pathlib import Path

from pydantic import BaseModel, Field

from ai_qa.exceptions import ConfigError


class LLMConfig(BaseModel):
    """Configuration for an LLM client."""

    provider: str = Field(
        default="litellm", description="LLM provider (e.g., litellm, openai, anthropic)"
    )
    model_name: str = Field(..., description="The name of the model to use")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0, description="Sampling temperature")
    base_url: str = Field(default="", description="Base URL for the API (e.g., LiteLLM proxy)")
    api_key: str = Field(default="", description="API key for the provider")
    max_retries: int = Field(
        default=3, ge=0, description="Maximum number of retries for transient errors"
    )

    @classmethod
    def from_agents_json(cls, agent_name: str, agents_file: Path | None = None) -> "LLMConfig":
        """Load configuration for a specific agent from agents.json file.

        Args:
            agent_name: Name of the agent (e.g., "bob", "mary", "sarah", "jack")
            agents_file: Path to agents.json file, defaults to workspace/configuration/agents.json

        Returns:
            LLMConfig instance with agent-specific settings

        Raises:
            FileNotFoundError: If agents.json file doesn't exist
            KeyError: If agent_name is not found in the configuration
        """
        if agents_file is None:
            agents_file = Path(
                os.getenv("AI_QA_AGENTS_CONFIG", "workspace/configuration/agents.json")
            )

        if not agents_file.exists():
            raise FileNotFoundError(f"Agents configuration file not found: {agents_file}")

        try:
            with open(agents_file) as f:
                agents_config = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"Invalid JSON in agents configuration: {e}") from e

        if "agents" not in agents_config:
            raise KeyError(f"Missing 'agents' key in configuration file: {agents_file}")

        if agent_name not in agents_config["agents"]:
            raise KeyError(f"Agent '{agent_name}' not found in configuration")

        agent_config = agents_config["agents"][agent_name]

        # Load provider configuration to get base_url and api_key info
        provider_file = agents_file.parent / "provider.json"
        provider_config = {}
        if provider_file.exists():
            with open(provider_file) as f:
                provider_config = json.load(f)

        endpoint = provider_config.get("endpoint", "")
        if not endpoint:
            raise ConfigError(f"Missing 'endpoint' in provider configuration: {provider_file}")

        # Load API key from environment based on credential_reference
        api_key = ""
        credential_ref = provider_config.get("credential_reference", "")
        if credential_ref.startswith("env://"):
            env_var = credential_ref[6:]  # Strip 'env://' prefix
            api_key = os.getenv(env_var, "")

        return cls(
            provider=provider_config.get("provider", "litellm"),
            model_name=agent_config["model"],
            temperature=agent_config.get("temperature", 0.0),
            base_url=endpoint,
            api_key=api_key,
            max_retries=3,
        )
