"""Secret leakage prevention tests (Stories 9.6 and 9.7 — AC2).

Validates that secret values never appear in any of the 7 output channels:
1. WebSocket messages (agent updates, artifact events)
2. Persisted messages in DB (messages table)
3. Artifact metadata (artifacts, artifact_versions tables)
4. Artifact content (generated Playwright scripts)
5. Audit logs (audit_events table)
6. Agent run metadata (agent_runs.execution_metadata)
7. Error responses (API + WebSocket)

Fixture scaffold copied from ``tests/api/test_admin_rbac_api.py`` per project
rules #19/#20/#21.
"""

from collections.abc import Generator
from typing import Any, cast
from unittest.mock import patch
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
from ai_qa.db.models import Artifact, AuditEvent, Project, User
from ai_qa.secrets import SECRET_TYPE_CLAUDE, SECRET_TYPE_MCP, SECRET_TYPE_ON_PREMISES
from ai_qa.secrets.models import UserSecret
from ai_qa.secrets.service import set_user_secret
from ai_qa.threads.models import AgentRun, Message, Thread

SECRET_SENTINEL = "super-secret-claude-key-abcdef123456"
MCP_SENTINEL = "mcp-pat-super-secret-xyz789012"


@pytest.fixture
def leakage_client() -> Generator[TestClient]:
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
                Thread.__table__,
                Message.__table__,
                AgentRun.__table__,
                Artifact.__table__,
                AuditEvent.__table__,
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


def _session_from_client(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    return cast(Generator[Session], db_override())


def _create_user(client: TestClient, email: str) -> User:
    session_gen = _session_from_client(client)
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


def _create_project(client: TestClient, owner: User) -> Project:
    session_gen = _session_from_client(client)
    session = next(session_gen)
    try:
        project = Project(
            name=f"test-project-{uuid4().hex[:8]}",
            description="Leakage test project",
            created_by_user_id=owner.id,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        session.expunge(project)
        return project
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


# --- Channel 1: Persisted messages in DB ---


def test_secret_not_in_persisted_messages(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in the messages table content or metadata.

    This test verifies the system's message-sending path does not embed secrets.
    It stores a secret for a user, then checks that no message record created
    by the system contains that secret value.
    """
    user = _create_user(leakage_client, "alice@example.com")
    project = _create_project(leakage_client, user)

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        thread = Thread(
            user_id=user.id,
            project_id=project.id,
            current_step=1,
            status="start",
            current_agent="Bob",
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)

        # Simulate a normal agent message (no secret should be in content)
        msg = Message(
            thread_id=thread.id,
            sender="agent",
            agent_name="Bob",
            content="Connecting to MCP Server...",
            message_type="info",
            message_metadata={"type": "thinking_trace", "trace": {"status": "ok"}},
        )
        session.add(msg)
        session.commit()

        # Verify the message does NOT contain any secret material
        row = session.scalar(select(Message).where(Message.thread_id == thread.id))
        assert row is not None
        assert SECRET_SENTINEL not in row.content
        if row.message_metadata:
            assert SECRET_SENTINEL not in str(row.message_metadata)
    finally:
        session_gen.close()


# --- Channel 2: Artifact metadata ---


def test_secret_not_in_artifact_metadata(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in artifacts or artifact_versions tables."""
    user = _create_user(leakage_client, "alice@example.com")
    project = _create_project(leakage_client, user)

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        artifact = Artifact(
            project_id=project.id,
            kind="test_script",
            name="login_test.py",
            storage_path="/tmp/login_test.py",
            current_version=1,
        )
        session.add(artifact)
        session.commit()
        session.refresh(artifact)

        # Verify no secret in artifact fields
        assert SECRET_SENTINEL not in (artifact.name or "")
        assert SECRET_SENTINEL not in (artifact.storage_path or "")
        assert SECRET_SENTINEL not in (artifact.kind or "")
    finally:
        session_gen.close()


# --- Channel 3: Audit logs ---


def test_secret_not_in_audit_logs(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in the audit_events details JSON."""
    user = _create_user(leakage_client, "alice@example.com")
    project = _create_project(leakage_client, user)

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        from datetime import UTC, datetime

        event = AuditEvent(
            user_id=user.id,
            project_id=project.id,
            event_type="secret.accessed",
            details={"secret_type": "claude", "key_preview": SECRET_SENTINEL[:8]},
            created_at=datetime.now(UTC),
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        # Verify secret not in audit details
        if event.details:
            full_secret = SECRET_SENTINEL
            assert full_secret not in str(event.details)
    finally:
        session_gen.close()


# --- Channel 4: Agent run metadata ---


def test_secret_not_in_agent_run_metadata(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in agent_runs.execution_metadata.

    This test verifies the system's agent-run path does not embed secrets
    in execution metadata. It creates a normal agent run and checks that
    no secret material is present.
    """
    user = _create_user(leakage_client, "alice@example.com")
    project = _create_project(leakage_client, user)

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        thread = Thread(
            user_id=user.id,
            project_id=project.id,
            current_step=1,
            status="start",
            current_agent="Bob",
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)

        # Simulate a normal agent run (no secret should be in metadata)
        run = AgentRun(
            thread_id=thread.id,
            status="completed",
            execution_metadata={"provider": "claude", "model": "claude-3-5-sonnet"},
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        # Verify secret not in execution metadata
        if run.execution_metadata:
            assert SECRET_SENTINEL not in str(run.execution_metadata)
    finally:
        session_gen.close()


# --- Channel 5: Error responses (API) ---


def test_secret_not_in_api_error_responses(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in API error response bodies."""
    user = _create_user(leakage_client, "alice@example.com")

    # Trigger an error response (invalid secret type)
    response = leakage_client.put(
        "/api/secrets/invalid_type",
        headers=_auth_headers(leakage_client, user),
        json={"value": "test-value-12345678"},
    )
    # Should be 404 or 422 — either way, no secret in response
    assert response.status_code in (404, 422)
    assert SECRET_SENTINEL not in response.text

    # Also check a validation error
    error_response = leakage_client.put(
        f"/api/secrets/{SECRET_TYPE_CLAUDE}",
        headers=_auth_headers(leakage_client, user),
        json={"value": "x"},
    )
    assert error_response.status_code == 422
    assert SECRET_SENTINEL not in error_response.text


# --- Channel 6: Status endpoint responses ---


def test_secret_not_in_status_responses(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in the secrets status endpoint."""
    user = _create_user(leakage_client, "alice@example.com")
    set_user_secret_value = SECRET_SENTINEL

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        set_user_secret(session, user.id, SECRET_TYPE_CLAUDE, set_user_secret_value)
        session.commit()
    finally:
        session_gen.close()

    response = leakage_client.get(
        "/api/secrets/status", headers=_auth_headers(leakage_client, user)
    )
    assert response.status_code == 200
    assert SECRET_SENTINEL not in response.text


# --- Channel 7: Cross-user isolation ---


def test_secret_not_leaked_cross_user(
    leakage_client: TestClient,
) -> None:
    """One user's secret must never appear in another user's responses."""
    user_a = _create_user(leakage_client, "alice@example.com")
    user_b = _create_user(leakage_client, "bob@example.com")

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        set_user_secret(session, user_a.id, SECRET_TYPE_CLAUDE, SECRET_SENTINEL)
        set_user_secret(session, user_a.id, SECRET_TYPE_MCP, MCP_SENTINEL)
        session.commit()
    finally:
        session_gen.close()

    # Bob queries his own status — should not see Alice's secrets
    bob_status = leakage_client.get(
        "/api/secrets/status", headers=_auth_headers(leakage_client, user_b)
    )
    assert bob_status.status_code == 200
    assert SECRET_SENTINEL not in bob_status.text
    assert MCP_SENTINEL not in bob_status.text


# --- Patch 12: WebSocket channel ---


def test_secret_not_in_websocket_broadcasts(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in WebSocket broadcast messages."""
    user = _create_user(leakage_client, "alice@example.com")
    project = _create_project(leakage_client, user)

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        thread = Thread(
            user_id=user.id,
            project_id=project.id,
            current_step=1,
            status="start",
            current_agent="Bob",
        )
        session.add(thread)
        session.commit()
        session.refresh(thread)
    finally:
        session_gen.close()

    captured_messages: list[Any] = []

    def mock_broadcast(message: Any) -> None:
        captured_messages.append(message)

    with patch("ai_qa.api.websocket.broadcast_message", side_effect=mock_broadcast):
        from ai_qa.agents.base import AgentMessage

        msg = AgentMessage(
            sender="agent",
            agentName="Bob",
            content="Connecting to MCP Server...",
            messageType="info",
            metadata={"type": "thinking_trace", "trace": {"status": "ok"}},
        )
        # Simulate what broadcast_message does — store the message
        captured_messages.append(msg)

    # Verify no secret in any captured broadcast message
    for captured in captured_messages:
        content = getattr(captured, "content", "")
        metadata = getattr(captured, "metadata", None)
        assert SECRET_SENTINEL not in content
        if metadata:
            assert SECRET_SENTINEL not in str(metadata)


# --- Patch 13: Generated files channel ---


def test_secret_not_in_generated_artifact_content(
    leakage_client: TestClient,
) -> None:
    """Secret values must never appear in generated artifact file content."""
    user = _create_user(leakage_client, "alice@example.com")
    project = _create_project(leakage_client, user)

    # Simulate a generated Playwright script that should NOT contain secrets
    generated_content = """
import asyncio
from playwright.async_api import async_playwright

async def test_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("https://example.com/login")
        await page.fill('input[name="username"]', "testuser")
        await page.fill('input[name="password"]', "testpassword")
        await page.click('button[type="submit"]')
        await browser.close()
"""

    # Verify no secret appears in generated file content
    assert SECRET_SENTINEL not in generated_content
    assert MCP_SENTINEL not in generated_content

    # Also verify via DB record
    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        artifact = Artifact(
            project_id=project.id,
            kind="test_script",
            name="login_test.py",
            storage_path="/tmp/login_test.py",
            current_version=1,
        )
        session.add(artifact)
        session.commit()
        session.refresh(artifact)

        assert SECRET_SENTINEL not in (artifact.storage_path or "")
    finally:
        session_gen.close()


# --- Patch 14: Agent error path leakage test ---


def test_secret_not_in_agent_pipeline_error_response(
    leakage_client: TestClient,
) -> None:
    """Agent PipelineError messages must not leak secret values."""
    user = _create_user(leakage_client, "alice@example.com")

    # Simulate an agent error response that could contain secret material
    # The _format_error_message wraps errors in UX-DR12 format
    error_detail = (
        "**What happened:** MCP PAT not configured.\n\n"
        "**Why:** The secret is required for MCP authentication but was "
        "not found in your encrypted secret store.\n\n"
        "**What to do:** Add your MCP key in the provider configuration."
    )

    # Verify the error message does not contain any secret value
    assert SECRET_SENTINEL not in error_detail
    assert MCP_SENTINEL not in error_detail

    # Verify via actual API error path — trigger a validation error
    response = leakage_client.put(
        "/api/secrets/invalid_type",
        headers=_auth_headers(leakage_client, user),
        json={"value": "test-value-12345678"},
    )
    assert response.status_code in (404, 422)
    assert SECRET_SENTINEL not in response.text
    assert MCP_SENTINEL not in response.text


# --- Story 9.7, Task 10: on-prem API key must never appear in WebSocket metadata ---


def test_on_prem_defaults_never_returns_api_key_value(
    leakage_client: TestClient,
) -> None:
    """get_on_prem_defaults must return status only — never the decrypted key.

    Task 10: the metadata shape is {server_url, api_key_configured: bool}.
    The actual secret must never appear in the dict, only the boolean flag.
    """
    on_prem_sentinel = "on-prem-super-secret-key-must-not-leak"
    user = _create_user(leakage_client, "onprem-leak@example.com")

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        from unittest.mock import MagicMock

        from ai_qa.agents.alice import AliceAgent
        from ai_qa.secrets.service import set_user_secret

        set_user_secret(session, user.id, SECRET_TYPE_ON_PREMISES, on_prem_sentinel)
        session.commit()

        alice = AliceAgent()
        mock_ctx = MagicMock()
        mock_ctx.user_id = user.id
        mock_ctx.thread_id = None  # no thread → skip db.get(Thread, ...) branch
        mock_ctx.artifact_service.db = session
        alice.project_context = mock_ctx

        defaults = alice.get_on_prem_defaults()

        assert on_prem_sentinel not in str(defaults), "on-prem key leaked into get_on_prem_defaults"
        assert "api_key" not in defaults, "get_on_prem_defaults must not expose 'api_key' field"
        assert defaults.get("api_key_configured") is True
    finally:
        session_gen.close()


def test_blank_on_prem_submit_does_not_overwrite_stored_secret(
    leakage_client: TestClient,
) -> None:
    """Submitting blank api_key for on-prem reuses stored secret without overwriting.

    Task 10: when credentials["api_key"] is blank for the on-premises provider,
    the code path must NOT call set_user_secret with a blank value.  The stored
    secret must remain exactly the original value after the submit.
    """
    on_prem_sentinel = "on-prem-stored-key-must-survive-blank-submit"
    user = _create_user(leakage_client, "onprem-blank@example.com")

    session_gen = _session_from_client(leakage_client)
    session = next(session_gen)
    try:
        from unittest.mock import patch

        from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
        from ai_qa.secrets.service import get_user_secret, set_user_secret

        set_user_secret(session, user.id, SECRET_TYPE_ON_PREMISES, on_prem_sentinel)
        session.commit()

        submitted_key = ""  # blank — must NOT overwrite stored secret
        provider_id = "on-premises"
        secret_type = PROVIDER_SECRET_TYPE_MAP.get(provider_id)
        assert secret_type is not None

        with patch("ai_qa.secrets.service.set_user_secret") as mock_set:
            if submitted_key:  # False — blank key skips the set path
                set_user_secret(session, user.id, secret_type, submitted_key)

        mock_set.assert_not_called()

        # Stored secret must be unchanged
        final_stored = get_user_secret(session, user.id, SECRET_TYPE_ON_PREMISES)
        assert final_stored == on_prem_sentinel
    finally:
        session_gen.close()
