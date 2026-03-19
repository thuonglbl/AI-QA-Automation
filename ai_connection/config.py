import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AIServerConfig:
    base_url: str
    api_key: str
    model: str
    timeout: float
    verify_ssl: bool
    http2: bool
    ca_bundle: str

    def __repr__(self) -> str:
        key_preview = self.api_key[:4] + "..." if self.api_key else "(empty)"
        return (
            f"AIServerConfig(base_url={self.base_url!r}, api_key={key_preview!r}, "
            f"model={self.model!r}, timeout={self.timeout}, "
            f"verify_ssl={self.verify_ssl}, http2={self.http2}, "
            f"ca_bundle={self.ca_bundle!r})"
        )


def load_config(path: str | None = None) -> AIServerConfig:
    """Load AI server config from YAML file.

    Path resolution: (1) explicit path, (2) AI_CONFIG_PATH env var,
    (3) config.yaml in project root (relative to this file).
    """
    if path is None:
        path = os.environ.get("AI_CONFIG_PATH")
    if path is None:
        path = str(Path(__file__).resolve().parent.parent / "config.yaml")

    config_path = Path(path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            "Copy config.example.yaml to config.yaml and fill in your values."
        )

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict) or "ai_server" not in raw:
        raise ValueError("Config file must contain an 'ai_server' section.")

    cfg = raw["ai_server"]

    # Required string fields
    base_url = str(cfg.get("base_url", "")).rstrip("/")
    if not base_url:
        raise ValueError("Config: 'base_url' is required and must be non-empty.")

    api_key = os.environ.get("AI_API_KEY") or str(cfg.get("api_key", ""))
    if not api_key:
        raise ValueError(
            "Config: 'api_key' is required. Set in config.yaml or AI_API_KEY env var."
        )

    model = str(cfg.get("model", ""))
    if not model:
        raise ValueError("Config: 'model' is required and must be non-empty.")

    # Numeric
    timeout = cfg.get("timeout", 120)
    try:
        timeout = float(timeout)
    except (TypeError, ValueError):
        raise ValueError(f"Config: 'timeout' must be a number, got: {timeout!r}")
    if timeout <= 0:
        raise ValueError(f"Config: 'timeout' must be > 0, got: {timeout}")

    # Booleans
    verify_ssl = bool(cfg.get("verify_ssl", True))
    http2 = bool(cfg.get("http2", True))

    # Optional CA bundle — resolve to absolute path
    ca_bundle = str(cfg.get("ca_bundle", "") or "")
    if ca_bundle:
        ca_bundle = str(Path(ca_bundle).resolve())
        if not Path(ca_bundle).exists():
            raise FileNotFoundError(f"Config: ca_bundle not found: {ca_bundle}")

    return AIServerConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=timeout,
        verify_ssl=verify_ssl,
        http2=http2,
        ca_bundle=ca_bundle,
    )
