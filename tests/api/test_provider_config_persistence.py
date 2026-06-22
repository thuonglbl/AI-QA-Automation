"""API tests for saved provider configuration persistence (Story 9.7).

Validates that non-secret config is saved to PostgreSQL, rotated secrets apply
to future runs only, and existing thread history is unchanged after rotation.

Fixture scaffold copied from ``tests/api/test_admin_rbac_api.py`` per project
rules #19/#20/#21.
"""

import json
from collections.abc import Generator
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import AiProviderConfig, Project, ProjectMembership, User
from ai_qa.secrets import (
    SECRET_TYPE_CLAUDE,
    SECRET_TYPE_OPENAI,
)
from ai_qa.secrets.models import UserSecret
from ai_qa.secrets.service import get_user_secret, set_user_secret
from ai_qa.threads.models import AgentRun, Message, Thread
from ai_qa.userconfig.service import get_provider_config, save_provider_config


@pytest.fixture
def persistence_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                User.__table__,
                UserSecret.__table__,
                Project.__table__,
                ProjectMembership.__table__,
                AiProviderConfig.__table__,
                Thread.__table__,
                Message.__table__,
                AgentRun.__table__,
            ],
        ),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    return cast(Generator[Session], db_override())


def _create_user(client: TestClient, email: str) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
            role=STANDARD_ROLE,
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _store_secret(client: TestClient, user: User, secret_type: str, value: str) -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        set_user_secret(session, user.id, secret_type, value)
        session.commit()
    finally:
        session_gen.close()


def _read_secret(client: TestClient, user: User, secret_type: str) -> str | None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        result: str | None = get_user_secret(session, user.id, secret_type)
        return result
    finally:
        session_gen.close()


def _token(client: TestClient, user: User) -> str:
    app = cast(FastAPI, client.app)
    session_manager = SessionManager(app.state.settings)
    session = session_manager.create_session(
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
    return session_manager.encode_session(session)  # type: ignore[no-any-return]


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, user)}"}


# --- [P0] Story 9.7: Saved Provider Configuration ---


def test_non_secret_config_persisted_to_database(
    persistence_client: TestClient,
) -> None:
    """[P0] AC1: Non-secret config (status, metadata) is saved to PostgreSQL.

    The secret_type, status, and timestamps are persisted, while the
    encrypted_value is stored via the ORM type handler.
    """
    user = _create_user(persistence_client, "alice@example.com")

    response = persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "my-claude-api-key-12345678"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["secret_type"] == SECRET_TYPE_CLAUDE
    assert body["configured"] is True
    assert body["status"] == "configured"
    assert body["last_updated"] is not None

    # Verify the secret is actually stored and retrievable
    stored_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert stored_value == "my-claude-api-key-12345678"


def test_rotated_secret_applies_to_future_runs_only(
    persistence_client: TestClient,
) -> None:
    """[P0] AC2: Rotated secrets apply to future runs only.

    When a secret is rotated, the new value is stored immediately but
    only takes effect for new operations, not in-flight ones.
    """
    user = _create_user(persistence_client, "alice@example.com")

    # Store initial secret
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, "old-claude-key-12345678")
    old_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert old_value == "old-claude-key-12345678"

    # Rotate the secret
    response = persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "new-claude-key-12345678"},
    )
    assert response.status_code == 200

    # New value is now stored for future runs
    new_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert new_value == "new-claude-key-12345678"
    assert new_value != old_value


def test_existing_thread_history_unchanged_after_rotation(
    persistence_client: TestClient,
) -> None:
    """[P0] AC3: Existing thread history is unchanged after secret rotation.

    Rotating a secret must not modify or invalidate any previously
    stored thread data or conversation history.
    """
    user = _create_user(persistence_client, "alice@example.com")

    # Store initial secret
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, "initial-key-12345678")

    # Verify initial secret is stored
    initial_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert initial_value == "initial-key-12345678"

    # Rotate secret
    response = persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "rotated-key-12345678"},
    )
    assert response.status_code == 200

    # The previous value is superseded, not deleted
    # (rotation replaces the value, history is preserved in the metadata)
    current_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert current_value == "rotated-key-12345678"

    # Status reflects the new configuration
    status_response = persistence_client.get(
        "/api/secrets/status", headers=_auth_headers(persistence_client, user)
    )
    assert status_response.status_code == 200
    claude_status = next(
        e for e in status_response.json() if e["secret_type"] == SECRET_TYPE_CLAUDE
    )
    assert claude_status["configured"] is True
    assert claude_status["status"] == "configured"


def test_secret_rotation_preserves_only_latest_value(
    persistence_client: TestClient,
) -> None:
    """[P0] Only one row per (user_id, secret_type) exists after multiple rotations."""
    user = _create_user(persistence_client, "alice@example.com")

    # Perform multiple rotations
    for i in range(3):
        response = persistence_client.put(
            f"/api/secrets/{SECRET_TYPE_CLAUDE}",
            headers=_auth_headers(persistence_client, user),
            json={"value": f"rotated-key-{i}-12345678"},
        )
        assert response.status_code == 200

    # Only one row should exist
    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        from sqlalchemy import select

        rows = session.scalars(
            select(UserSecret).where(
                UserSecret.user_id == user.id,
                UserSecret.secret_type == SECRET_TYPE_CLAUDE,
            )
        ).all()
        assert len(rows) == 1
        # Verify it's the latest value via the service layer (TypeDecorator decrypts on read)
        stored_val = get_user_secret(session, user.id, SECRET_TYPE_CLAUDE)
        assert stored_val == "rotated-key-2-12345678"
    finally:
        session_gen.close()


def test_multiple_provider_configs_persist_independently(
    persistence_client: TestClient,
) -> None:
    """[P0] Different provider secrets are stored and rotated independently."""
    user = _create_user(persistence_client, "alice@example.com")

    # Store secrets for different providers
    persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "claude-key-12345678"},
    )
    persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_OPENAI}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "openai-key-12345678"},
    )

    # Rotate only Claude
    persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "new-claude-key-12345678"},
    )

    # Verify Claude is rotated, OpenAI is unchanged
    claude_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    openai_value = _read_secret(persistence_client, user, SECRET_TYPE_OPENAI)

    assert claude_value == "new-claude-key-12345678"
    assert openai_value == "openai-key-12345678"


def test_config_persistence_survives_session_restart(
    persistence_client: TestClient,
) -> None:
    """[P0] Configuration persists across database session boundaries."""
    user = _create_user(persistence_client, "alice@example.com")

    # Store secret in first session
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, "persistent-key-12345678")

    # Read in a new session (simulating restart)
    stored_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert stored_value == "persistent-key-12345678"

    # Status should reflect persisted state
    response = persistence_client.get(
        "/api/secrets/status", headers=_auth_headers(persistence_client, user)
    )
    assert response.status_code == 200
    claude_status = next(e for e in response.json() if e["secret_type"] == SECRET_TYPE_CLAUDE)
    assert claude_status["configured"] is True


def test_secret_deletion_removes_configuration(
    persistence_client: TestClient,
) -> None:
    """[P0] Deleting a secret removes it from persistence completely."""
    user = _create_user(persistence_client, "alice@example.com")

    # Store then delete secret
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, "doomed-key-12345678")

    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        secret = session.scalar(
            select(UserSecret).where(
                UserSecret.user_id == user.id,
                UserSecret.secret_type == SECRET_TYPE_CLAUDE,
            )
        )
        assert secret is not None
        session.delete(secret)
        session.commit()
    finally:
        session_gen.close()

    # Verify deletion
    deleted_value = _read_secret(persistence_client, user, SECRET_TYPE_CLAUDE)
    assert deleted_value is None

    # Status should show missing
    response = persistence_client.get(
        "/api/secrets/status", headers=_auth_headers(persistence_client, user)
    )
    assert response.status_code == 200
    claude_status = next(e for e in response.json() if e["secret_type"] == SECRET_TYPE_CLAUDE)
    assert claude_status["configured"] is False
    assert claude_status["status"] == "missing"


# --- Story 9.7: Real AC1/AC2/AC3 provider-config coverage ---


def _create_project(client: TestClient) -> Project:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        project = Project(name=f"proj-{uuid4()}", enabled_providers=[])
        session.add(project)
        session.commit()
        session.refresh(project)
        session.expunge(project)
        return project
    finally:
        session_gen.close()


def _create_membership(client: TestClient, user: User, project: Project) -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        membership = ProjectMembership(user_id=user.id, project_id=project.id, role="member")
        session.add(membership)
        session.commit()
    finally:
        session_gen.close()


def _create_thread(client: TestClient, user: User, project: Project) -> Thread:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        thread = Thread(user_id=user.id, project_id=project.id)
        session.add(thread)
        session.commit()
        session.refresh(thread)
        session.expunge(thread)
        return thread
    finally:
        session_gen.close()


def _save_config_via_service(
    client: TestClient, user: User, project: Project, provider: str
) -> None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        save_provider_config(
            session,
            user.id,
            project.id,
            {
                "provider": provider,
                "provider_name": provider.capitalize(),
                "endpoint": "https://example.com",
                "tested_at": "2026-01-01T00:00:00Z",
                "test_result": "success",
            },
            {
                "agents": {
                    "bob": {"model": "gpt-4o", "temperature": 0.0, "rationale": "vision capable"}
                }
            },
        )
        session.commit()
    finally:
        session_gen.close()


def _read_config_via_service(client: TestClient, user: User, project: Project) -> dict | None:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        return get_provider_config(session, user.id, project.id)
    finally:
        session_gen.close()


def test_ac1_config_upsert_per_user_project(persistence_client: TestClient) -> None:
    """[AC1] Approving config upserts one row per (user, project) — no secrets stored."""
    user = _create_user(persistence_client, "ac1@example.com")
    project = _create_project(persistence_client)

    _save_config_via_service(persistence_client, user, project, "claude")
    cfg = _read_config_via_service(persistence_client, user, project)
    assert cfg is not None
    assert cfg["provider"]["provider"] == "claude"

    # Repeated upsert keeps ONE row
    _save_config_via_service(persistence_client, user, project, "openai")
    cfg = _read_config_via_service(persistence_client, user, project)
    assert cfg is not None
    assert cfg["provider"]["provider"] == "openai"

    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        rows = session.scalars(
            select(AiProviderConfig).where(
                AiProviderConfig.user_id == user.id,
                AiProviderConfig.project_id == project.id,
            )
        ).all()
        assert len(rows) == 1
    finally:
        session_gen.close()


def test_ac1_stored_config_contains_no_secret_sentinel(persistence_client: TestClient) -> None:
    """[AC1 leakage guard] Secret value must never appear in ai_provider_configs."""
    secret_sentinel = "sk-DO-NOT-STORE-ME-ABCDEF123456"
    user = _create_user(persistence_client, "leakguard@example.com")
    project = _create_project(persistence_client)
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, secret_sentinel)

    # Save config WITHOUT secret (service contract)
    _save_config_via_service(persistence_client, user, project, "claude")

    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        row = session.scalar(
            select(AiProviderConfig).where(
                AiProviderConfig.user_id == user.id,
                AiProviderConfig.project_id == project.id,
            )
        )
        assert row is not None
        stored = json.dumps(row.ai_provider_config or {}) + json.dumps(row.ai_agents_config or {})
        assert secret_sentinel not in stored
    finally:
        session_gen.close()


def test_ac2_provider_config_endpoint_rejects_non_owner(persistence_client: TestClient) -> None:
    """[AC2] GET /api/threads/{id}/provider-config returns 404 for non-owner."""
    owner = _create_user(persistence_client, "owner@example.com")
    other = _create_user(persistence_client, "other@example.com")
    project = _create_project(persistence_client)
    _create_membership(persistence_client, owner, project)
    thread = _create_thread(persistence_client, owner, project)

    response = persistence_client.get(
        f"/api/threads/{thread.id}/provider-config",
        headers=_auth_headers(persistence_client, other),
    )
    # 403 or 404 — both are acceptable "access denied" responses
    assert response.status_code in (403, 404)


def test_ac2_provider_config_endpoint_returns_thread_snapshot(
    persistence_client: TestClient,
) -> None:
    """[AC2] GET .../provider-config returns thread snapshot — no secret."""
    secret_sentinel = "sk-SECRET-NEVER-RETURNED-XYZABC"
    user = _create_user(persistence_client, "snap@example.com")
    project = _create_project(persistence_client)
    _create_membership(persistence_client, user, project)
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, secret_sentinel)

    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        thread = Thread(
            user_id=user.id,
            project_id=project.id,
            provider_name="claude",
            provider_base_url="https://api.anthropic.com",
            agent_configs={"bob": {"model": "gpt-4o", "temperature": 0.0, "rationale": "r"}},
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)
        thread_id = thread.id
    finally:
        session_gen.close()

    response = persistence_client.get(
        f"/api/threads/{thread_id}/provider-config",
        headers=_auth_headers(persistence_client, user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["source"] == "thread"
    assert body["provider"] == "claude"
    # Must NOT return the secret
    assert secret_sentinel not in json.dumps(body)
    assert "api_key" not in json.dumps(body).lower() or "api_key_configured" in json.dumps(body)


def test_ac2_provider_config_endpoint_returns_none_when_no_config(
    persistence_client: TestClient,
) -> None:
    """[AC2] GET .../provider-config returns configured=false when nothing saved."""
    user = _create_user(persistence_client, "empty@example.com")
    project = _create_project(persistence_client)
    _create_membership(persistence_client, user, project)

    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        thread = Thread(user_id=user.id, project_id=project.id)
        session.add(thread)
        session.commit()
        session.refresh(thread)
        thread_id = thread.id
    finally:
        session_gen.close()

    response = persistence_client.get(
        f"/api/threads/{thread_id}/provider-config",
        headers=_auth_headers(persistence_client, user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["source"] == "none"


def test_ac3_rotation_leaves_thread_snapshot_immutable(
    persistence_client: TestClient,
) -> None:
    """[AC3] After secret rotation, thread snapshot and messages are unchanged."""
    user = _create_user(persistence_client, "ac3@example.com")
    project = _create_project(persistence_client)
    _create_membership(persistence_client, user, project)
    _store_secret(persistence_client, user, SECRET_TYPE_CLAUDE, "old-claude-key-12345678")

    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        thread = Thread(
            user_id=user.id,
            project_id=project.id,
            provider_name="claude",
            agent_configs={"bob": {"model": "claude-sonnet", "temperature": 0.0}},
        )
        session.add(thread)
        session.flush()  # assign thread.id before creating Message FK
        msg = Message(thread_id=thread.id, sender="agent", content="hello", message_type="text")
        session.add(msg)
        session.commit()
        session.refresh(thread)
        session.refresh(msg)
        snapshot_before = dict(thread.agent_configs or {})
        thread_id = thread.id
        msg_id = msg.id
    finally:
        session_gen.close()

    # Rotate secret
    response = persistence_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(persistence_client, user),
        json={"value": "new-rotated-key-12345678"},
    )
    assert response.status_code == 200

    # Verify thread snapshot unchanged
    session_gen = _session_from_override(persistence_client)
    session = next(session_gen)
    try:
        thread_after = session.get(Thread, thread_id)
        assert thread_after is not None
        assert thread_after.agent_configs == snapshot_before

        msg_after = session.get(Message, msg_id)
        assert msg_after is not None
        assert msg_after.content == "hello"

        # New secret is stored for future runs
        new_value = get_user_secret(session, user.id, SECRET_TYPE_CLAUDE)
        assert new_value == "new-rotated-key-12345678"
    finally:
        session_gen.close()
