# Standard library
from pathlib import Path

# Third-party
from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Project root resolved at import time relative to this file (not CWD)
_PROJECT_ROOT = Path(__file__).parents[2]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    # --- LLM Provider (FR14, FR15) ---
    anthropic_api_key: str = Field(
        default="", description="Claude API key (optional if using on-prem)"
    )
    on_premises_ai_server_url: str = Field(default="", description="On-prem LiteLLM proxy base URL")
    on_premises_ai_server_key: str = Field(default="", description="On-prem AI server API key")

    # --- LLM Parameters (FR15) ---
    llm_model: str = Field(default="claude-sonnet-4-6", description="LLM model identifier")
    llm_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="LLM sampling temperature"
    )

    # --- Server ---
    server_host: str = Field(default="0.0.0.0", description="Server bind host")
    server_port: int = Field(default=8000, ge=1, le=65535, description="Server bind port")

    # --- MCP (FR14) ---
    mcp_server_url: str = Field(
        default="", description="MCP server URL for Confluence/Jira integration"
    )
    mcp_server_key: str = Field(default="", description="MCP server API key")
    mcp_timeout: int = Field(
        default=30, ge=1, le=300, description="MCP connection timeout in seconds"
    )
    mcp_max_retries: int = Field(
        default=3, ge=0, le=10, description="Max retry attempts for MCP operations"
    )
    mcp_retry_backoff: float = Field(
        default=1.0, ge=0.1, le=10.0, description="Retry backoff multiplier in seconds"
    )

    # --- Browser (FR12, NFR2, NFR7, NFR8) ---
    chrome_path: str = Field(
        default="", description="Path to Chrome executable for browser automation"
    )
    browser_timeout: int = Field(
        default=30, ge=1, le=300, description="Browser action timeout in seconds"
    )

    # --- Script Generation (FR6-9, NFR14) ---
    script_generation_model: str = Field(
        default="sonnet", description="Model for script generation (can override per-agent config)"
    )
    script_generation_temperature: float = Field(
        default=0.0, ge=0.0, le=2.0, description="Temperature for deterministic script output"
    )
    script_generation_timeout: int = Field(
        default=120, ge=10, le=600, description="Timeout in seconds per script generation"
    )
    max_script_length: int = Field(
        default=10000, ge=1000, le=50000, description="Maximum characters per generated script"
    )
    confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Threshold to flag low confidence generations"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        config_yaml = _PROJECT_ROOT / "config.yaml"
        sources: list[PydanticBaseSettingsSource] = [
            init_settings,
            env_settings,
            dotenv_settings,
        ]
        if config_yaml.exists():
            sources.append(YamlConfigSettingsSource(settings_cls, yaml_file=config_yaml))
        return tuple(sources)
