# Standard library
import hashlib
import re
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus, urlsplit, urlunsplit

# Third-party
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

# Project root resolved at import time relative to this file (not CWD)
_PROJECT_ROOT = Path(__file__).parents[2]

# Execution run policy (Story 14.2). Typed constant so the Literal default is not
# inferred as plain `str` (Pyrefly bad-assignment / mypy).
RunPolicy = Literal["continue", "stop_on_first_failure"]
_DEFAULT_RUN_POLICY: RunPolicy = "continue"


def validate_execution_output_prefix(value: str) -> str:
    """Validate a logical execution-output prefix (Story 14.3, AC2 fail-fast).

    Rejects empty/whitespace, absolute paths, Windows drive-letter/UNC prefixes,
    and any ``..`` traversal segment. Cross-platform (POSIX + Windows). Used by both
    the ``AppSettings`` field validator (startup) and the adapter runtime guard.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("execution_output_prefix must not be empty.")
    normalized = cleaned.replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError("execution_output_prefix must be a relative path, not absolute.")
    if re.match(r"^[A-Za-z]:", cleaned) or normalized.startswith("//"):
        raise ValueError("execution_output_prefix must not be a drive-letter or UNC path.")
    if any(segment == ".." for segment in normalized.split("/")):
        raise ValueError("execution_output_prefix must not contain '..' path traversal.")
    return cleaned


def get_user_workspace_dir(user_email: str) -> Path:
    """Get per-user workspace directory path (hashed for filesystem safety).

    Args:
        user_email: User's email address.

    Returns:
        Path to user's workspace directory.
    """
    email_hash = hashlib.sha256(user_email.lower().encode()).hexdigest()[:16]
    return _PROJECT_ROOT / "workspace" / "users" / f"{email_hash}_{user_email.split('@')[0]}"


class UserConfig(BaseModel):
    """Per-user configuration model.

    Contains user-specific settings like API keys that were previously in shared .env.
    """

    anthropic_api_key: str = Field(default="", description="User's Claude API key")
    openai_api_key: str = Field(default="", description="User's OpenAI API key")
    gemini_api_key: str = Field(default="", description="User's Google Gemini API key")
    browser_use_api_key: str = Field(default="", description="User's Browser Use Cloud API key")
    on_premises_ai_server_url: str = Field(default="", description="User's on-prem LiteLLM proxy")
    on_premises_ai_server_key: str = Field(
        default="", description="User's on-prem AI server API key"
    )
    llm_model: str = Field(default="claude-sonnet-4-6", description="Preferred LLM model")
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    # --- Session Security (Story 11-1) ---
    session_secret_key: str = Field(
        default="dev-secret-change-in-production",
        description="Secret key for signing session cookies",
    )
    session_expire_hours: int = Field(
        default=8, ge=1, le=24, description="Session expiration in hours"
    )
    session_cookie_name: str = Field(default="aiqa_session", description="Name of session cookie")
    session_cookie_secure: bool = Field(
        default=False, description="Use Secure flag for cookies (enable in production with HTTPS)"
    )
    session_cookie_samesite: str = Field(
        default="Lax", description="SameSite attribute for cookies"
    )

    # --- Server ---
    server_host: str = Field(default="0.0.0.0", description="Server bind host")
    server_port: int = Field(default=8000, ge=1, le=65535, description="Server bind port")

    # --- External Service URLs ---
    browser_use_cloud_url: str = Field(
        default="https://api.browser-use.com/api/v2", description="Browser Use Cloud API base URL"
    )
    claude_api_base_url: str = Field(
        default="https://api.anthropic.com", description="Claude API base URL"
    )
    gemini_api_base_url: str = Field(
        default="https://generativelanguage.googleapis.com", description="Gemini API base URL"
    )
    openai_api_base_url: str = Field(
        default="https://api.openai.com", description="OpenAI API base URL"
    )
    on_premises_api_base_url: str = Field(default="", description="On-Premises API base URL")

    # --- Model sync (admin "Sync models and benchmarks") ---
    # Server-side provider keys used ONLY by the admin model-discovery sync. They map
    # from the TEST_<PROVIDER>_KEY env vars (case-insensitive). Resolved at runtime,
    # never returned to the frontend or logged.
    test_claude_key: str = Field(default="", description="Server key for Claude model discovery")
    test_openai_key: str = Field(default="", description="Server key for OpenAI model discovery")
    test_gemini_key: str = Field(default="", description="Server key for Gemini model discovery")
    test_on_premises_key: str = Field(
        default="", description="Server key for on-premises model discovery"
    )
    test_browser_use_key: str = Field(
        default="", description="Server key for Browser Use Cloud model discovery"
    )
    # llm-stats.com Data API — structured benchmark scores per model (free Bearer key,
    # no usage limits, updated within hours of model release). Empty key => the benchmark
    # half of the sync is skipped (model discovery still runs).
    llm_stats_api_key: str = Field(
        default="", description="llm-stats.com Data API Bearer key (ze_…)"
    )
    llm_stats_api_base_url: str = Field(
        default="https://api.llm-stats.com/stats/v1",
        description="llm-stats.com Data API base URL",
    )

    # --- Claude SSO (enterprise OAuth login) ---
    # When ``claude_sso_authorize_url`` is empty, the backend serves a built-in
    # mock IdP login page (dev/E2E). When set, it points at the real OAuth
    # authorization endpoint (e.g. Anthropic Team-plan SSO), which federates to
    # the company IdP. The token obtained from the flow is stored as the per-user
    # ``claude_sso`` secret; it is never returned to the frontend.
    claude_sso_authorize_url: str = Field(
        default="", description="OAuth authorize URL ('' = use built-in mock IdP page)"
    )
    claude_sso_token_url: str = Field(
        default="", description="OAuth token-exchange URL (real-OAuth mode only)"
    )
    claude_sso_client_id: str = Field(
        default="", description="OAuth client id (real-OAuth mode only)"
    )
    claude_sso_redirect_uri: str = Field(
        default="", description="OAuth redirect URI ('' = backend /api/auth/claude-sso/callback)"
    )
    claude_sso_enterprise_api_key: str = Field(
        default="",
        description=(
            "Server-side Claude Enterprise license key used for actual model calls "
            "after a successful SSO login in mock/demo mode. Deployment config, not a "
            "per-user secret. Never logged or returned to the frontend."
        ),
    )
    claude_sso_allowed_email_domain: str = Field(
        default="",
        description="If set, the mock IdP only accepts emails on this domain.",
    )

    # --- MCP (FR14) ---
    mcp_server_url: str = Field(
        default="", description="MCP server URL for Confluence/Jira integration"
    )
    mcp_tool_prefix: str = Field(default="", description="Prefix for MCP tools")
    mcp_use_streamable_http: bool = Field(
        default=True, description="Use MCP Streamable HTTP transport instead of Legacy SSE"
    )
    mcp_timeout: int = Field(
        default=120, ge=1, le=300, description="MCP connection timeout in seconds"
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

    # --- Test Execution (Jack, Story 14.2) ---
    execution_timeout: int = Field(
        default=120,
        ge=10,
        le=1800,
        description="Per-script execution timeout in seconds (pytest --timeout-equivalent)",
    )
    execution_wall_clock_timeout: int = Field(
        default=900,
        ge=30,
        le=7200,
        description="Hard wall-clock cap (seconds) for the whole execution subprocess",
    )
    run_policy: RunPolicy = Field(
        default=_DEFAULT_RUN_POLICY,
        description=(
            "Execution run policy: 'continue' runs every selected script even on failure; "
            "'stop_on_first_failure' stops at the first failing test (-x)."
        ),
    )

    # --- Execution Output (Jack, Story 14.3) ---
    execution_output_prefix: str = Field(
        default="runs",
        description=(
            "Logical name prefix for persisted execution outputs; artifacts are named "
            "'{prefix}/{run_id}/{file}'. Relative path only (validated at startup)."
        ),
    )
    execution_capture_screenshots: bool = Field(
        default=True, description="Persist execution screenshots through the artifact service"
    )
    execution_capture_traces: bool = Field(
        default=True, description="Persist execution Playwright traces through the artifact service"
    )
    execution_capture_logs: bool = Field(
        default=True, description="Persist the execution run log through the artifact service"
    )
    execution_overwrite_reports: bool = Field(
        default=False,
        description="Allow overwriting an existing run's persisted outputs (AC3 explicit switch)",
    )

    @field_validator("execution_output_prefix")
    @classmethod
    def _validate_execution_output_prefix(cls, value: str) -> str:
        """Fail fast on a malformed execution-output prefix (Story 14.3 AC2)."""
        return validate_execution_output_prefix(value)

    confidence_threshold: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Threshold to flag low confidence generations"
    )
    script_unsafe_patterns: list[str] = Field(
        default_factory=list,
        description=(
            "Additional/override disallowed patterns for generated scripts (FR21). "
            "When non-empty, replaces DEFAULT_UNSAFE_SCRIPT_PATTERNS entirely."
        ),
    )

    # --- PostgreSQL Persistence (Story 12-1) ---
    database_url: str = Field(default="", description="Full SQLAlchemy database URL")
    database_host: str = Field(default="localhost", description="PostgreSQL host")
    database_port: int = Field(default=5432, ge=1, le=65535, description="PostgreSQL port")
    database_name: str = Field(default="ai_qa_automation", description="PostgreSQL database name")
    database_user: str = Field(default="ai_qa", description="PostgreSQL username")
    database_password: str = Field(default="", description="PostgreSQL password")
    database_pool_size: int = Field(default=5, ge=1, description="SQLAlchemy pool size")
    database_max_overflow: int = Field(default=10, ge=0, description="SQLAlchemy max overflow")
    database_echo: bool = Field(
        default=False, description="Echo SQL statements for local debugging"
    )
    db_encryption_key: str = Field(
        default="ozjY9J56PAawdLJw5Lp8HfL0YUO4NP_PpKNWxgvxGb0=",
        description="Key for Fernet encryption of DB columns",
    )

    # --- User Secret Encryption (Story 9.1) ---
    user_secrets_encryption_key: str = Field(
        default="",
        description=(
            "Fernet key for encrypting per-user AI provider / MCP secrets. "
            "Required at startup; never stored in the database."
        ),
    )

    @field_validator("user_secrets_encryption_key")
    @classmethod
    def _validate_user_secrets_encryption_key(cls, value: str) -> str:
        """Fail fast when the user-secrets encryption key is missing or invalid.

        AC3: startup validation must reject a missing or non-Fernet key with an
        actionable error. ``AppSettings`` is instantiated at import time in
        ``ai_qa.api`` so this validator fails the process fast on boot.
        """
        actionable = (
            "USER_SECRETS_ENCRYPTION_KEY is missing or invalid. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
        if not value:
            raise ValueError(actionable)
        try:
            Fernet(value.encode("utf-8"))
        except Exception as exc:
            raise ValueError(actionable) from exc
        return value

    # --- S3 Compatible Storage (SeaweedFS) ---
    seaweedfs_endpoint: str = Field(
        default="localhost:8333", description="SeaweedFS server endpoint"
    )
    seaweedfs_access_key: str = Field(default="admin", description="SeaweedFS access key")
    seaweedfs_secret_key: str = Field(
        default="seaweedfspassword", description="SeaweedFS secret key"
    )
    seaweedfs_secure: bool = Field(default=False, description="Use HTTPS for SeaweedFS storage")
    seaweedfs_bucket: str = Field(
        default="ai-qa-artifacts", description="Bucket for storing artifacts"
    )
    s3_connect_timeout: int = Field(
        default=1, description="Connection timeout for S3/SeaweedFS clients"
    )
    s3_read_timeout: int = Field(default=1, description="Read timeout for S3/SeaweedFS clients")

    @property
    def sqlalchemy_database_url(self) -> str:
        """Return a SQLAlchemy-compatible PostgreSQL URL from settings.

        DATABASE_URL takes precedence. Otherwise individual DATABASE_* settings
        are assembled with URL escaping so credentials are safe for special chars.
        """
        if self.database_url:
            return self.database_url

        user = quote_plus(self.database_user)
        password = quote_plus(self.database_password)
        auth = f"{user}:{password}@" if password else f"{user}@"
        host = self.database_host
        return f"postgresql+psycopg://{auth}{host}:{self.database_port}/{self.database_name}"

    @property
    def masked_database_url(self) -> str:
        """Return the database URL with any password hidden for safe logging."""
        return mask_database_url(self.sqlalchemy_database_url)

    # --- Vision-Assisted Locator Identification (FR5, NFR1) ---
    vision_enabled: bool = Field(
        default=True, description="Enable vision-assisted locator identification"
    )
    vision_model: str = Field(default="sonnet", description="Vision model for element analysis")
    vision_timeout: int = Field(
        default=60, ge=10, le=300, description="Timeout in seconds for vision analysis"
    )
    vision_screenshot_quality: int = Field(
        default=85, ge=1, le=100, description="JPEG quality for screenshots (1-100)"
    )
    locator_validation_enabled: bool = Field(
        default=True, description="Validate locators against actual DOM"
    )
    vision_fallback_on_error: bool = Field(
        default=True, description="Fallback to LLM-only when vision fails"
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


def mask_database_url(database_url: str) -> str:
    """Mask credentials in a SQLAlchemy database URL without leaking secrets."""
    if not database_url:
        return ""

    parts = urlsplit(database_url)
    if not parts.netloc or "@" not in parts.netloc:
        return database_url

    credentials, host = parts.netloc.rsplit("@", 1)
    if ":" in credentials:
        username, _password = credentials.split(":", 1)
        credentials = f"{username}:***"
    else:
        credentials = "***"
    return urlunsplit(
        (parts.scheme, f"{credentials}@{host}", parts.path, parts.query, parts.fragment)
    )
