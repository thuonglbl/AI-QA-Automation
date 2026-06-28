"""API + service tests for per-user captured browser sessions."""

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_qa.db.models import Project, ProjectMembership, User
from ai_qa.sessions import service as session_service

_CAPTURE = "ai_qa.api.sessions.capture_storage_state_over_cdp"
_HTTPX_CLIENT = "ai_qa.api.sessions.httpx.AsyncClient"
FAKE_STATE: dict[str, object] = {
    "cookies": [{"name": "sid", "value": "secret", "domain": "t1.app", "path": "/"}],
    "origins": [],
}


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
        assert "login_type" not in data
        assert data["captured"] == []

    def test_list_returns_saved_session(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        admin = db_session.query(User).filter(User.email == "admin@example.com").one()

        session_service.save_captured_session(
            db_session,
            user_id=admin.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
            auth_method="SSO_MANUAL",
            storage_state=FAKE_STATE,
        )

        listed = client.get(
            f"/api/projects/{project.id}/sessions",
            headers={"Authorization": f"Bearer {admin_token}"},
        ).json()
        assert len(listed["captured"]) == 1
        assert listed["captured"][0]["environment"] == "Test 1"
        assert listed["captured"][0]["role"] == "Admin"
        assert listed["captured"][0]["cookie_count"] == 1

    def test_delete_removes_session(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        admin = db_session.query(User).filter(User.email == "admin@example.com").one()
        headers = {"Authorization": f"Bearer {admin_token}"}

        session_service.save_captured_session(
            db_session,
            user_id=admin.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
            auth_method="SSO_MANUAL",
            storage_state=FAKE_STATE,
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


def _multi_env_project(db: Session) -> Project:
    """A project with a reachable env, a connect-erroring env, and a blank-URL env."""
    project = Project(
        name="Multi Env Project",
        confluence_base_url="https://confluence.example.com",
        enabled_providers=["openai"],
        environments=[
            {"name": "Reachable", "url": "https://ok.app"},
            {"name": "Dead", "url": "https://dead.app"},
            {"name": "Unconfigured", "url": ""},
        ],
        app_roles=["Admin", "User"],
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _async_client_per_url(by_url: dict[str, object], default_error: Exception) -> MagicMock:
    """Mock ``httpx.AsyncClient`` whose ``.get(url)`` returns/raises per requested URL.

    ``by_url`` maps a URL to either an ``httpx.Response`` (returned) or an ``Exception``
    (raised); any URL not present raises ``default_error``.
    """

    async def _get(url: str, *args: object, **kwargs: object) -> object:
        outcome = by_url.get(url, default_error)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client_obj = MagicMock()
    client_obj.get = AsyncMock(side_effect=_get)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_obj)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=ctx)


class TestCheckConnectionsApi:
    """POST /environments/check-connections — server-side per-environment reachability probe."""

    def test_batch_probe_reports_each_environment(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _multi_env_project(db_session)
        by_url: dict[str, object] = {
            "https://ok.app": httpx.Response(status_code=302),
            "https://dead.app": httpx.ConnectError("nope"),
        }
        factory = _async_client_per_url(by_url, default_error=httpx.ConnectError("nope"))
        with patch(_HTTPX_CLIENT, new=factory):
            resp = client.post(
                f"/api/projects/{project.id}/environments/check-connections",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200, resp.text
        results = {r["name"]: r for r in resp.json()["results"]}
        assert len(results) == 3

        # A 302 redirect (e.g. to a login page) counts as reachable.
        reachable = results["Reachable"]
        assert reachable["reachable"] is True
        assert reachable["status_code"] == 302
        assert reachable["url"] == "https://ok.app"

        # A connect error counts as unreachable, no status code.
        dead = results["Dead"]
        assert dead["reachable"] is False
        assert dead["status_code"] is None
        assert "connect" in dead["detail"].lower()

        # A blank-URL env is skipped from probing and reported as not configured.
        blank = results["Unconfigured"]
        assert blank["reachable"] is False
        assert blank["status_code"] is None
        assert "no url" in blank["detail"].lower()

    def test_timeout_is_not_reachable(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        factory = _async_client_per_url({}, default_error=httpx.ConnectTimeout("slow"))
        with patch(_HTTPX_CLIENT, new=factory):
            resp = client.post(
                f"/api/projects/{project.id}/environments/check-connections",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        assert resp.status_code == 200, resp.text
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["reachable"] is False
        assert "timed out" in results[0]["detail"].lower()

    def test_non_member_cannot_check(
        self, client: TestClient, user_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        resp = client.post(
            f"/api/projects/{project.id}/environments/check-connections",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        # require_project_member_or_admin hides non-member projects as 404.
        assert resp.status_code == 404
