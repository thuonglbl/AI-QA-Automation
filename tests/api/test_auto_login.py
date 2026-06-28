from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from ai_qa.db.models import Project, TestAccountCredential
from ai_qa.exceptions import BrowserError, ConfigError
from ai_qa.sessions import auto_login
from ai_qa.sessions import service as session_service


@pytest.fixture
def mock_generate() -> Any:
    with patch(
        "ai_qa.sessions.auto_login.generate_session_storage_state", new_callable=AsyncMock
    ) as m:
        m.return_value = {"cookies": [{"name": "new", "value": "123"}], "origins": []}
        yield m


@pytest.mark.asyncio
async def test_resolve_or_generate_uses_cache_if_valid(db_session: Session) -> None:
    # Set up basic project and user
    user_id = uuid4()
    project_id = uuid4()

    # Save a valid session (no expiration or future expiration)
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    fake_blob = {"cookies": [{"name": "valid", "value": "xyz"}], "origins": []}
    session_service.save_captured_session(
        db_session,
        user_id=user_id,
        project_id=project_id,
        environment="Test",
        role="Admin",
        auth_method="TEST_ACCOUNT",
        storage_state=fake_blob,
        expires_at=expires_at,
    )

    result = await auto_login.resolve_or_generate_storage_state(
        db_session, user_id, project_id, "Test", "Admin", chrome_path=""
    )
    assert result == fake_blob


@pytest.mark.asyncio
async def test_resolve_or_generate_triggers_generation_if_cache_miss(
    db_session: Session, mock_generate: AsyncMock
) -> None:
    user_id = uuid4()
    project = Project(
        name="AutoLogin Project",
        environments=[{"name": "Test", "url": "https://test.app"}],
        app_roles=["Admin"],
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    cred = TestAccountCredential(
        user_id=user_id,
        project_id=project.id,
        environment="Test",
        role="Admin",
        username="admin",
        password="test-secret",
    )
    db_session.add(cred)
    db_session.commit()

    # Cache is empty initially
    result = await auto_login.resolve_or_generate_storage_state(
        db_session, user_id, project.id, "Test", "Admin", chrome_path="/usr/bin/google-chrome"
    )

    mock_generate.assert_called_once()
    assert result == {"cookies": [{"name": "new", "value": "123"}], "origins": []}

    # Verify that it was saved with a TTL
    saved = session_service.list_session_status(db_session, user_id=user_id, project_id=project.id)
    assert len(saved) == 1
    assert saved[0].environment == "Test"
    assert saved[0].role == "Admin"


@pytest.mark.asyncio
async def test_resolve_returns_none_when_no_credential_by_default(db_session: Session) -> None:
    """Fail-soft contract (Sarah/Jack): no credential -> None, never raises."""
    result = await auto_login.resolve_or_generate_storage_state(
        db_session, uuid4(), uuid4(), "Test", "Admin", chrome_path=""
    )
    assert result is None


@pytest.mark.asyncio
async def test_resolve_raise_on_failure_no_credential_raises_configerror(
    db_session: Session,
) -> None:
    """raise_on_failure (Test Login button): missing credential -> clear ConfigError."""
    with pytest.raises(ConfigError, match="No saved test credentials"):
        await auto_login.resolve_or_generate_storage_state(
            db_session, uuid4(), uuid4(), "Test", "Admin", chrome_path="", raise_on_failure=True
        )


@pytest.mark.asyncio
async def test_resolve_raise_on_failure_reraises_browsererror(db_session: Session) -> None:
    """raise_on_failure: a failed login attempt propagates its BrowserError (real reason)."""
    user_id = uuid4()
    project = Project(
        name="AutoLogin Project 3",
        environments=[{"name": "Test", "url": "https://test.app"}],
        app_roles=["Admin"],
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    db_session.add(
        TestAccountCredential(
            user_id=user_id,
            project_id=project.id,
            environment="Test",
            role="Admin",
            username="admin",
            password="test-secret",
        )
    )
    db_session.commit()

    with patch(
        "ai_qa.sessions.auto_login.generate_session_storage_state", new_callable=AsyncMock
    ) as m:
        m.side_effect = BrowserError("Could not resolve the target host", details="ERR_NAME...")
        with pytest.raises(BrowserError, match="Could not resolve the target host"):
            await auto_login.resolve_or_generate_storage_state(
                db_session,
                user_id,
                project.id,
                "Test",
                "Admin",
                chrome_path="",
                raise_on_failure=True,
            )


@pytest.mark.asyncio
async def test_resolve_or_generate_triggers_generation_if_cache_expired(
    db_session: Session, mock_generate: AsyncMock
) -> None:
    user_id = uuid4()
    project = Project(
        name="AutoLogin Project 2",
        environments=[{"name": "Test", "url": "https://test.app"}],
        app_roles=["Admin"],
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    cred = TestAccountCredential(
        user_id=user_id,
        project_id=project.id,
        environment="Test",
        role="Admin",
        username="admin",
        password="test-secret",
    )
    db_session.add(cred)
    db_session.commit()

    # Save an EXPIRED session
    expires_at = datetime.now(UTC) - timedelta(hours=1)
    fake_blob = {"cookies": [{"name": "expired", "value": "abc"}], "origins": []}
    session_service.save_captured_session(
        db_session,
        user_id=user_id,
        project_id=project.id,
        environment="Test",
        role="Admin",
        auth_method="TEST_ACCOUNT",
        storage_state=fake_blob,
        expires_at=expires_at,
    )

    # It should miss the cache because of expiration, and generate a new one
    result = await auto_login.resolve_or_generate_storage_state(
        db_session, user_id, project.id, "Test", "Admin", chrome_path="/usr/bin/google-chrome"
    )

    mock_generate.assert_called_once()
    assert result == {"cookies": [{"name": "new", "value": "123"}], "origins": []}
