"""API + service tests for per-user captured browser sessions."""

from collections.abc import Callable

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
