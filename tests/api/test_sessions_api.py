"""API + service tests for per-user captured browser sessions."""

from collections.abc import Callable
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_qa.api import sessions as sessions_api
from ai_qa.api.sessions import _provider_credential, _resolve_browser_use_llm
from ai_qa.browser.password_login import PasswordLoginError
from ai_qa.browser.session_capture import SessionCaptureError
from ai_qa.config import AppSettings
from ai_qa.db.models import Project, ProjectAccount, ProjectMembership, User
from ai_qa.sessions import service as session_service
from ai_qa.sessions.auto_capture import (
    AutoCaptureError,
    _environment_url,
    auto_capture_password_session,
    resolve_project_account,
)

_CAPTURE = "ai_qa.api.sessions.capture_storage_state_over_cdp"
# The orchestration resolves its login driver by NAME at call time, so patching this module
# attribute swaps the real browser launch for a stub in API tests.
_AUTO_DRIVER = "ai_qa.sessions.auto_capture.login_and_capture_storage_state"
FAKE_STATE: dict[str, object] = {
    "cookies": [{"name": "sid", "value": "secret", "domain": "t1.app", "path": "/"}],
    "origins": [],
}
# A password value that must NEVER appear in any response body or raised error.
SECRET_PW = "pw-secret-123"


def _project_with_matrix(db: Session) -> Project:
    project = Project(
        name="Sess Project",
        confluence_base_url="https://confluence.example.com",
        enabled_providers=["openai"],
        environments=[{"name": "Test 1", "url": "https://t1.app"}],
        app_roles=["Admin", "User"],
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestSessionsApi:
    def test_list_empty_returns_matrix(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        resp = client.get(
            f"/api/projects/{project.id}/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["app_roles"] == ["Admin", "User"]
        assert data["environments"] == [{"name": "Test 1", "url": "https://t1.app"}]
        assert data["login_type"] == "SSO"  # default when unset
        assert data["captured"] == []

    def test_matrix_reports_password_login_type(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _password_project(db_session)
        resp = client.get(
            f"/api/projects/{project.id}/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["login_type"] == "PASSWORD"

    def test_capture_then_list(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        with patch(_CAPTURE, new=AsyncMock(return_value=FAKE_STATE)):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/capture",
                json={"environment": "Test 1", "role": "Admin"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["environment"] == "Test 1"
        assert body["role"] == "Admin"
        assert body["auth_method"] == "SSO_MANUAL"
        assert body["cookie_count"] == 1
        # The session blob / cookies must NEVER be serialized to the client.
        assert "cookies" not in body
        assert "storage_state" not in body
        assert "secret" not in resp.text

        listed = client.get(
            f"/api/projects/{project.id}/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert len(listed["captured"]) == 1
        assert listed["captured"][0]["cookie_count"] == 1

    def test_capture_rejects_unknown_env_and_role(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        headers = {"Authorization": f"Bearer {admin_token}"}
        with patch(_CAPTURE, new=AsyncMock(return_value=FAKE_STATE)):
            bad_env = client.post(
                f"/api/projects/{project.id}/sessions/capture",
                json={"environment": "Nope", "role": "Admin"},
                headers=headers,
            )
            bad_role = client.post(
                f"/api/projects/{project.id}/sessions/capture",
                json={"environment": "Test 1", "role": "Ghost"},
                headers=headers,
            )
        assert bad_env.status_code == 422
        assert bad_role.status_code == 422

    def test_capture_cdp_failure_is_400(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        with patch(_CAPTURE, new=AsyncMock(side_effect=SessionCaptureError("no browser"))):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/capture",
                json={"environment": "Test 1", "role": "Admin"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 400

    def test_delete_removes_session(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        headers = {"Authorization": f"Bearer {admin_token}"}
        with patch(_CAPTURE, new=AsyncMock(return_value=FAKE_STATE)):
            client.post(
                f"/api/projects/{project.id}/sessions/capture",
                json={"environment": "Test 1", "role": "Admin"},
                headers=headers,
            )
        deleted = client.delete(
            f"/api/projects/{project.id}/sessions",
            params={"environment": "Test 1", "role": "Admin"},
            headers=headers,
        )
        assert deleted.status_code == 204
        listed = client.get(f"/api/projects/{project.id}/sessions", headers=headers).json()
        assert listed["captured"] == []

    def test_non_member_cannot_access(
        self, client: TestClient, user_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        resp = client.get(
            f"/api/projects/{project.id}/sessions",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # require_project_member_or_admin hides non-member projects as 404.
        assert resp.status_code == 404


class TestSessionService:
    def test_resolve_returns_blob_save_updates_in_place(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("sess@example.com")
        project = _project_with_matrix(db_session)
        db_session.add(ProjectMembership(project_id=project.id, user_id=user.id, role="member"))
        db_session.commit()

        session_service.save_captured_session(
            db_session,
            user_id=user.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
            auth_method="SSO_MANUAL",
            storage_state=FAKE_STATE,
        )
        # resolve returns the decrypted blob (the only reader that exposes it)
        resolved = session_service.resolve_storage_state(
            db_session,
            user_id=user.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
        )
        assert resolved == FAKE_STATE

        # re-capture overwrites in place (unique key), not a second row
        session_service.save_captured_session(
            db_session,
            user_id=user.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
            auth_method="PASSWORD",
            storage_state={"cookies": [], "origins": []},
        )
        statuses = session_service.list_session_status(
            db_session, user_id=user.id, project_id=project.id
        )
        assert len(statuses) == 1
        assert statuses[0].auth_method == "PASSWORD"
        assert statuses[0].cookie_count == 0


def _password_project(
    db: Session,
    *,
    name: str = "PW Project",
    login_type: str = "PASSWORD",
    with_account: bool = True,
    with_password: bool = True,
    providers: list[str] | None = None,
) -> Project:
    """A PASSWORD project with a Test 1 / Admin login account (configurable)."""
    project = Project(
        name=name,
        confluence_base_url="https://confluence.example.com",
        enabled_providers=providers or ["openai"],
        environments=[{"name": "Test 1", "url": "https://t1.app/login"}],
        app_roles=["Admin", "User"],
        login_type=login_type,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    if with_account:
        db.add(
            ProjectAccount(
                project_id=project.id,
                environment="Test 1",
                role="Admin",
                login_identifier="admin@t1.app",
                encrypted_password=SECRET_PW if with_password else None,
                label="Admin",
            )
        )
        db.commit()
        db.refresh(project)
    return project


class TestAutoCaptureService:
    """Orchestration: resolve account → drive login (injected) → save PASSWORD session."""

    async def test_happy_path_saves_password_session(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("auto@example.com")
        project = _password_project(db_session)
        captured: dict[str, object] = {}

        async def fake_driver(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return FAKE_STATE

        status = await auto_capture_password_session(
            db_session,
            user_id=user.id,
            project=project,
            environment="Test 1",
            role="Admin",
            chrome_path="C:/chrome.exe",
            capture_fn=fake_driver,
        )

        assert status.auth_method == "PASSWORD"
        assert status.cookie_count == 1
        # The driver received the resolved login URL + the project account credential.
        assert captured["login_url"] == "https://t1.app/login"
        assert captured["username"] == "admin@t1.app"
        assert captured["password"] == SECRET_PW
        # The session was persisted under THIS user and is resolvable for rehydration.
        resolved = session_service.resolve_storage_state(
            db_session,
            user_id=user.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
        )
        assert resolved == FAKE_STATE
        # The non-secret status never carries the password.
        assert SECRET_PW not in repr(status)

    async def test_sso_project_rejected(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("sso@example.com")
        project = _password_project(db_session, name="SSO Project", login_type="SSO")

        async def fake_driver(**_: object) -> dict[str, object]:
            return FAKE_STATE

        with pytest.raises(AutoCaptureError) as ei:
            await auto_capture_password_session(
                db_session,
                user_id=user.id,
                project=project,
                environment="Test 1",
                role="Admin",
                chrome_path="C:/chrome.exe",
                capture_fn=fake_driver,
            )
        assert ei.value.status_code == 409

    async def test_unknown_environment_and_role(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("env@example.com")
        project = _password_project(db_session)

        async def fake_driver(**_: object) -> dict[str, object]:
            return FAKE_STATE

        with pytest.raises(AutoCaptureError) as bad_env:
            await auto_capture_password_session(
                db_session,
                user_id=user.id,
                project=project,
                environment="Nope",
                role="Admin",
                chrome_path="c",
                capture_fn=fake_driver,
            )
        assert bad_env.value.status_code == 422

        with pytest.raises(AutoCaptureError) as bad_role:
            await auto_capture_password_session(
                db_session,
                user_id=user.id,
                project=project,
                environment="Test 1",
                role="Ghost",
                chrome_path="c",
                capture_fn=fake_driver,
            )
        assert bad_role.value.status_code == 422

    async def test_missing_account_is_404(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("noacct@example.com")
        project = _password_project(db_session, with_account=False)

        async def fake_driver(**_: object) -> dict[str, object]:
            return FAKE_STATE

        with pytest.raises(AutoCaptureError) as ei:
            await auto_capture_password_session(
                db_session,
                user_id=user.id,
                project=project,
                environment="Test 1",
                role="Admin",
                chrome_path="c",
                capture_fn=fake_driver,
            )
        assert ei.value.status_code == 404

    async def test_account_without_password_is_422(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("nopw@example.com")
        project = _password_project(db_session, with_password=False)

        async def fake_driver(**_: object) -> dict[str, object]:
            return FAKE_STATE

        with pytest.raises(AutoCaptureError) as ei:
            await auto_capture_password_session(
                db_session,
                user_id=user.id,
                project=project,
                environment="Test 1",
                role="Admin",
                chrome_path="c",
                capture_fn=fake_driver,
            )
        assert ei.value.status_code == 422

    async def test_login_failure_is_502_without_leaking_password(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("fail@example.com")
        project = _password_project(db_session)

        async def boom(**_: object) -> dict[str, object]:
            raise PasswordLoginError("Could not find a password field on the login page.")

        with pytest.raises(AutoCaptureError) as ei:
            await auto_capture_password_session(
                db_session,
                user_id=user.id,
                project=project,
                environment="Test 1",
                role="Admin",
                chrome_path="c",
                capture_fn=boom,
            )
        assert ei.value.status_code == 502
        assert SECRET_PW not in str(ei.value)


class TestAutoCaptureApi:
    """POST /sessions/auto-capture — real endpoint + orchestration, browser launch stubbed."""

    def test_auto_capture_then_list(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _password_project(db_session)
        with patch(_AUTO_DRIVER, new=AsyncMock(return_value=FAKE_STATE)):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/auto-capture",
                json={"environment": "Test 1", "role": "Admin", "chrome_path": "C:/chrome.exe"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["auth_method"] == "PASSWORD"
        assert body["cookie_count"] == 1
        # Neither the session blob nor the password is ever serialized to the client.
        assert "secret" not in resp.text
        assert SECRET_PW not in resp.text

        listed = client.get(
            f"/api/projects/{project.id}/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert listed["captured"][0]["auth_method"] == "PASSWORD"

    def test_sso_project_is_409(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _password_project(db_session, name="SSO Project", login_type="SSO")
        with patch(_AUTO_DRIVER, new=AsyncMock(return_value=FAKE_STATE)):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/auto-capture",
                json={"environment": "Test 1", "role": "Admin", "chrome_path": "c"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 409

    def test_missing_account_is_404(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _password_project(db_session)  # only Admin has an account; ask for User
        with patch(_AUTO_DRIVER, new=AsyncMock(return_value=FAKE_STATE)):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/auto-capture",
                json={"environment": "Test 1", "role": "User", "chrome_path": "c"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 404

    def test_login_failure_is_502(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _password_project(db_session)
        driver = AsyncMock(side_effect=PasswordLoginError("Could not find a password field."))
        with patch(_AUTO_DRIVER, new=driver):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/auto-capture",
                json={"environment": "Test 1", "role": "Admin", "chrome_path": "c"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 502
        assert SECRET_PW not in resp.text

    def test_non_member_cannot_auto_capture(
        self, client: TestClient, user_token: str, db_session: Session
    ) -> None:
        project = _password_project(db_session)
        resp = client.post(
            f"/api/projects/{project.id}/sessions/auto-capture",
            json={"environment": "Test 1", "role": "Admin", "chrome_path": "c"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 404

    def test_unknown_provider_still_captures_scripted_only(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        """A provider with no browser-use default (on-premises) → llm=None, scripted-only."""
        project = _password_project(db_session, providers=["on-premises"])
        driver = AsyncMock(return_value=FAKE_STATE)
        with patch(_AUTO_DRIVER, new=driver):
            resp = client.post(
                f"/api/projects/{project.id}/sessions/auto-capture",
                json={"environment": "Test 1", "role": "Admin", "chrome_path": "C:/chrome.exe"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200, resp.text
        aw = driver.await_args
        assert aw is not None
        assert aw.kwargs["llm"] is None


class TestBrowserUseLlmResolver:
    """Best-effort LLM-fallback resolver: returns None on any miss, never raises/500."""

    def test_unknown_provider_returns_none(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("res1@example.com")
        project = _password_project(db_session, providers=["on-premises"])
        assert _resolve_browser_use_llm(db_session, user, project, AppSettings()) is None

    def test_no_credential_returns_none(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("res2@example.com")
        project = _password_project(db_session, providers=["openai"])
        # No user secret + empty server key → no credential → None (scripted-only).
        assert _resolve_browser_use_llm(db_session, user, project, AppSettings()) is None

    def test_build_error_is_swallowed_to_none(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("res3@example.com")
        project = _password_project(db_session, providers=["claude"])
        with (
            patch.object(sessions_api, "get_user_secret", return_value="sk-key"),
            patch.object(sessions_api, "build_browser_use_llm", side_effect=RuntimeError("boom")),
        ):
            assert _resolve_browser_use_llm(db_session, user, project, AppSettings()) is None

    def test_builds_llm_when_credential_present(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("res4@example.com")
        project = _password_project(db_session, providers=["claude"])
        sentinel = object()
        with (
            patch.object(sessions_api, "get_user_secret", return_value="sk-key"),
            patch.object(sessions_api, "build_browser_use_llm", return_value=sentinel) as build,
        ):
            result = _resolve_browser_use_llm(db_session, user, project, AppSettings())
        assert result is sentinel
        assert build.call_args.args[0] == "claude"

    def test_claude_sso_falls_back_to_enterprise_key(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        user = user_factory("res5@example.com")
        settings = AppSettings(claude_sso_enterprise_api_key="ent-key")
        # No per-user claude_sso secret → enterprise key is used.
        api_key, base_url = _provider_credential(db_session, user, "claude-sso", settings)
        assert api_key == "ent-key"
        assert base_url == settings.claude_api_base_url


class TestAutoCaptureHelpers:
    """Pure resolution helpers in the orchestration layer."""

    def test_environment_url_resolution_and_edge_cases(self) -> None:
        project = cast(
            Project,
            SimpleNamespace(
                environments=[
                    {"name": "Prod", "url": "https://prod.app/login"},
                    {"name": "Blank", "url": "  "},
                    {"name": "NoUrl"},
                ]
            ),
        )
        assert _environment_url(project, "Prod") == "https://prod.app/login"
        assert _environment_url(project, "Blank") is None  # whitespace → None
        assert _environment_url(project, "NoUrl") is None  # missing url key → None
        assert _environment_url(project, "Ghost") is None  # unknown env → None

    def test_resolve_project_account_matches_env_and_role(self, db_session: Session) -> None:
        project = _password_project(db_session)  # Test 1 / Admin account exists
        found = resolve_project_account(
            db_session, project_id=project.id, environment="Test 1", role="Admin"
        )
        assert found is not None
        assert found.login_identifier == "admin@t1.app"
        # No account for (Test 1, User).
        assert (
            resolve_project_account(
                db_session, project_id=project.id, environment="Test 1", role="User"
            )
            is None
        )
