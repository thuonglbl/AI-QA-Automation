"""Thin accessor service for per-(user, project) non-secret AI provider config.

JSON shapes stored in ``ai_provider_configs``:

``ai_provider_config``:
    {"provider": str, "provider_name": str, "endpoint": str,
     "tested_at": str, "test_result": "success"|"failed", "rationale": str}

``ai_agents_config``:
    {"version": str, "updated_at": str,
     "agents": {<agent_name>: {"model": str, "temperature": float,
                               "prompt_template": str, "tools": list[str],
                               "rationale": str}}}

The caller is responsible for committing the session (mirrors secrets/service.py).
Secrets (API keys) MUST NEVER be stored here — AC1 leakage guard.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.db.models import AiProviderConfig


def save_provider_config(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    provider_config: dict[str, Any],
    agents_config: dict[str, Any],
) -> None:
    """Upsert the single (user_id, project_id) saved-config row.

    Performs a SELECT-then-update/insert (mirrors set_user_secret). The caller
    must commit the session. Secrets must not appear in either dict.

    Args:
        db: Active SQLAlchemy session.
        user_id: Owning user id.
        project_id: Bound project id.
        provider_config: Non-secret provider metadata dict.
        agents_config: Non-secret per-agent model/settings dict.
    """
    row = db.scalar(
        select(AiProviderConfig).where(
            AiProviderConfig.user_id == user_id,
            AiProviderConfig.project_id == project_id,
        )
    )
    if row is None:
        row = AiProviderConfig(
            user_id=user_id,
            project_id=project_id,
            ai_provider_config=provider_config,
            ai_agents_config=agents_config,
        )
        db.add(row)
    else:
        # Assign new dicts so SQLAlchemy flags the JSON columns as dirty.
        row.ai_provider_config = dict(provider_config)
        row.ai_agents_config = dict(agents_config)


def get_provider_config(
    db: Session,
    user_id: UUID,
    project_id: UUID,
) -> dict[str, Any] | None:
    """Return the saved (user, project) config or None when absent.

    Returns:
        {"provider": dict, "agents": dict} or None.
    """
    row = db.scalar(
        select(AiProviderConfig).where(
            AiProviderConfig.user_id == user_id,
            AiProviderConfig.project_id == project_id,
        )
    )
    if row is None:
        return None
    return {"provider": row.ai_provider_config, "agents": row.ai_agents_config}
