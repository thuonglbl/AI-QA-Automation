"""API tests for test credentials management."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_qa.db.models import Project, ProjectMembership, TestAccountCredential, User


def _project_with_matrix(db: Session) -> Project:
    project = Project(
        name="Creds Project",
        confluence_base_url="https://confluence.example.com",
        enabled_providers=["openai"],
        environments=[{"name": "Test 1", "url": "https://t1.app"}],
        app_roles=["Admin", "User"],
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestTestCredentialsApi:
    def test_list_empty(self, client: TestClient, admin_token: str, db_session: Session) -> None:
        project = _project_with_matrix(db_session)
        resp = client.get(
            f"/api/projects/{project.id}/test-credentials",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_upsert_and_list_strips_secrets(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Upsert
        resp = client.put(
            f"/api/projects/{project.id}/test-credentials",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "username": "test.admin@example.com",
                "password": "secretpassword",
                "totp_secret": "MYSECRET",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["environment"] == "Test 1"
        assert data["role"] == "Admin"
        assert data["username"] == "test.admin@example.com"
        assert "id" in data

        # Leak-canary test: responses must NOT contain password or totp_secret
        assert "password" not in data
        assert "totp_secret" not in data
        assert "secretpassword" not in resp.text
        assert "MYSECRET" not in resp.text

        # Verify list also strips secrets
        list_resp = client.get(f"/api/projects/{project.id}/test-credentials", headers=headers)
        assert list_resp.status_code == 200
        items = list_resp.json()
        assert len(items) == 1
        assert items[0]["id"] == data["id"]
        assert "password" not in items[0]
        assert "totp_secret" not in items[0]
        assert "secretpassword" not in list_resp.text
        assert "MYSECRET" not in list_resp.text

        # Verify DB storage uses encryption
        cred = db_session.query(TestAccountCredential).filter_by(id=uuid.UUID(data["id"])).first()
        assert cred is not None
        assert (
            cred.password == "secretpassword"
        )  # SQLAlchemy returns decrypted value seamlessly due to TypeDecorator

    def test_upsert_updates_existing(
        self, client: TestClient, admin_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        headers = {"Authorization": f"Bearer {admin_token}"}

        client.put(
            f"/api/projects/{project.id}/test-credentials",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "username": "test.admin@example.com",
                "password": "p1",
            },
            headers=headers,
        )

        resp = client.put(
            f"/api/projects/{project.id}/test-credentials",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "username": "new.admin@example.com",
                "password": "p2",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "new.admin@example.com"

        # Should only be one credential for this env/role
        items = client.get(f"/api/projects/{project.id}/test-credentials", headers=headers).json()
        assert len(items) == 1
        assert items[0]["username"] == "new.admin@example.com"

    def test_delete(self, client: TestClient, admin_token: str, db_session: Session) -> None:
        project = _project_with_matrix(db_session)
        headers = {"Authorization": f"Bearer {admin_token}"}

        upsert_resp = client.put(
            f"/api/projects/{project.id}/test-credentials",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "username": "test.admin@example.com",
                "password": "p1",
            },
            headers=headers,
        )
        cred_id = upsert_resp.json()["id"]

        del_resp = client.delete(
            f"/api/projects/{project.id}/test-credentials/{cred_id}", headers=headers
        )
        assert del_resp.status_code == 204

        items = client.get(f"/api/projects/{project.id}/test-credentials", headers=headers).json()
        assert len(items) == 0

    def test_delete_also_clears_captured_session(
        self, client: TestClient, token_factory, db_user: User, db_session: Session
    ) -> None:
        """Deleting a credential must also drop its captured session (no orphan session)."""
        from ai_qa.sessions import service as session_service

        project = _project_with_matrix(db_session)
        db_session.add(ProjectMembership(project_id=project.id, user_id=db_user.id, role="member"))
        db_session.commit()
        headers = {"Authorization": f"Bearer {token_factory(db_user)}"}

        cred_id = client.put(
            f"/api/projects/{project.id}/test-credentials",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "username": "test.admin@example.com",
                "password": "p1",
            },
            headers=headers,
        ).json()["id"]

        # Simulate a captured login session for the same (env, role) slot.
        session_service.save_captured_session(
            db_session,
            user_id=db_user.id,
            project_id=project.id,
            environment="Test 1",
            role="Admin",
            auth_method="PASSWORD",
            storage_state={"cookies": [], "origins": []},
        )
        assert (
            len(
                session_service.list_session_status(
                    db_session, user_id=db_user.id, project_id=project.id
                )
            )
            == 1
        )

        del_resp = client.delete(
            f"/api/projects/{project.id}/test-credentials/{cred_id}", headers=headers
        )
        assert del_resp.status_code == 204

        db_session.expire_all()
        assert (
            session_service.list_session_status(
                db_session, user_id=db_user.id, project_id=project.id
            )
            == []
        )

    def test_non_member_cannot_list(
        self, client: TestClient, user_token: str, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        resp = client.get(
            f"/api/projects/{project.id}/test-credentials",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 404

    def test_member_can_manage_own_credentials(
        self, client: TestClient, token_factory, db_user: User, db_session: Session
    ) -> None:
        project = _project_with_matrix(db_session)
        db_session.add(ProjectMembership(project_id=project.id, user_id=db_user.id, role="member"))
        db_session.commit()
        token = token_factory(db_user)
        headers = {"Authorization": f"Bearer {token}"}

        # Can upsert
        put_resp = client.put(
            f"/api/projects/{project.id}/test-credentials",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "username": "test.admin@example.com",
                "password": "p1",
            },
            headers=headers,
        )
        assert put_resp.status_code == 200
        cred_id = put_resp.json()["id"]

        # Can list
        resp = client.get(f"/api/projects/{project.id}/test-credentials", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Can delete
        del_resp = client.delete(
            f"/api/projects/{project.id}/test-credentials/{cred_id}",
            headers=headers,
        )
        assert del_resp.status_code == 204
