import pytest
from pydantic import ValidationError


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
