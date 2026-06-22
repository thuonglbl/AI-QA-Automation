import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

# A valid Fernet key for positive-path config tests that isolate from the
# project .env (which already supplies a real key at the repo root).
_VALID_FERNET_KEY = Fernet.generate_key().decode()


def test_appsettings_loads_with_defaults(tmp_path, monkeypatch):
    """AppSettings initializes with defaults when no config.yaml present at project root."""
    import ai_qa.config as cfg

    # Ensure no config.yaml exists at project root during this test
    config_yaml = cfg._PROJECT_ROOT / "config.yaml"
    existed_before = config_yaml.exists()
    if existed_before:
        pytest.skip("Skipping: real config.yaml exists at project root")

    settings = cfg.AppSettings()
    assert settings.script_generation_model == "sonnet"
    assert settings.script_generation_temperature == 0.0


def test_appsettings_env_var_overrides_default(tmp_path, monkeypatch):
    """Env vars override default values."""
    monkeypatch.chdir(tmp_path)  # isolate from project .env
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", _VALID_FERNET_KEY)
    monkeypatch.setenv("SCRIPT_GENERATION_MODEL", "gpt-4o")
    monkeypatch.setenv("SCRIPT_GENERATION_TEMPERATURE", "0.5")
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    settings = cfg.AppSettings()
    assert settings.script_generation_model == "gpt-4o"
    assert settings.script_generation_temperature == 0.5


def test_appsettings_temperature_validation(tmp_path, monkeypatch):
    """Temperature outside [0.0, 2.0] raises ValidationError."""
    monkeypatch.chdir(tmp_path)  # isolate from project .env
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", _VALID_FERNET_KEY)
    monkeypatch.setenv("SCRIPT_GENERATION_TEMPERATURE", "3.0")
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    with pytest.raises(ValidationError):
        cfg.AppSettings()


def test_appsettings_str_strip_whitespace(monkeypatch):
    """Whitespace-only URL values are stripped to empty string."""
    monkeypatch.setenv("CHROME_PATH", "   ")
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    settings = cfg.AppSettings()
    assert settings.chrome_path == ""


def test_user_secrets_encryption_key_missing_raises(tmp_path, monkeypatch):
    """AC3: a missing USER_SECRETS_ENCRYPTION_KEY fails fast with ValidationError."""
    monkeypatch.chdir(tmp_path)  # isolate from project .env
    monkeypatch.delenv("USER_SECRETS_ENCRYPTION_KEY", raising=False)
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    with pytest.raises(ValidationError, match="USER_SECRETS_ENCRYPTION_KEY"):
        cfg.AppSettings()


def test_user_secrets_encryption_key_invalid_raises(tmp_path, monkeypatch):
    """AC3: a non-Fernet USER_SECRETS_ENCRYPTION_KEY fails fast with ValidationError."""
    monkeypatch.chdir(tmp_path)  # isolate from project .env
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    with pytest.raises(ValidationError, match="USER_SECRETS_ENCRYPTION_KEY"):
        cfg.AppSettings()


def test_user_secrets_encryption_key_valid_loads(tmp_path, monkeypatch):
    """AC3: a valid generated Fernet key loads successfully."""
    monkeypatch.chdir(tmp_path)  # isolate from project .env
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", _VALID_FERNET_KEY)
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    settings = cfg.AppSettings()
    assert settings.user_secrets_encryption_key == _VALID_FERNET_KEY


# ---------------------------------------------------------------------------
# Story 14.3: execution_output_prefix validation (AC2 fail-fast)
# ---------------------------------------------------------------------------


def test_validate_execution_output_prefix_accepts_clean_relative() -> None:
    """A clean relative prefix is accepted and stripped."""
    from ai_qa.config import validate_execution_output_prefix

    assert validate_execution_output_prefix("  runs  ") == "runs"
    assert validate_execution_output_prefix("runs/executions") == "runs/executions"


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "/abs/path", "C:/win/path", r"\\unc\share", "runs/../etc", ".."],
)
def test_validate_execution_output_prefix_rejects_unsafe(bad: str) -> None:
    """Empty, absolute, drive-letter/UNC, and '..' traversal prefixes are rejected."""
    from ai_qa.config import validate_execution_output_prefix

    with pytest.raises(ValueError):
        validate_execution_output_prefix(bad)


def test_appsettings_rejects_bad_execution_output_prefix(tmp_path, monkeypatch) -> None:
    """AppSettings fails fast on a malformed EXECUTION_OUTPUT_PREFIX."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("USER_SECRETS_ENCRYPTION_KEY", _VALID_FERNET_KEY)
    monkeypatch.setenv("EXECUTION_OUTPUT_PREFIX", "/absolute/bad")
    from importlib import reload

    import ai_qa.config as cfg

    reload(cfg)
    with pytest.raises(ValidationError):
        cfg.AppSettings()
