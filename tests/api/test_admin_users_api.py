"""API tests for admin user management endpoints."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_qa.db.models import Project, User


class TestAdminUserCreate:
    def test_create_user_valid(self, client: TestClient, admin_token: str) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "newuser@test.com",
                "display_name": "New User",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert data["is_active"] is True
        # Defaults to UTC when the admin omits a timezone.
        assert data["timezone"] == "UTC"
        # Defaults to "en" for conversation_language
        assert data["conversation_language"] == "en"

    def test_create_user_with_timezone(self, client: TestClient, admin_token: str) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "tzuser@test.com",
                "display_name": "TZ User",
                "role": "standard",
                "timezone": "Asia/Ho_Chi_Minh",
                "conversation_language": "vi",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["timezone"] == "Asia/Ho_Chi_Minh"
        assert response.json()["conversation_language"] == "vi"

    def test_create_user_invalid_timezone_rejected(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "badtz@test.com",
                "display_name": "Bad TZ",
                "role": "standard",
                "timezone": "Not/AZone",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_create_user_invalid_language_rejected(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "badlang@test.com",
                "display_name": "Bad Lang",
                "role": "standard",
                "conversation_language": "Vietnamese",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_create_user_duplicate_email(
        self, client: TestClient, admin_token: str, db_user: User
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": db_user.email,
                "display_name": "Duplicate",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    def test_non_admin_cannot_create_user(self, client: TestClient, user_token: str) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "hacker@test.com",
                "display_name": "Hacker",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestAdminUserDelete:
    def test_delete_user(self, client: TestClient, admin_token: str, db_user: User) -> None:
        response = client.delete(
            f"/api/admin/users/{db_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

    def test_delete_nonexistent_user(
        self, client: TestClient, admin_token: str, fake_uuid: object
    ) -> None:
        response = client.delete(
            f"/api/admin/users/{fake_uuid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestAdminUserCreateProjectAdmin:
    """Story 15.3 — project_admin users are linked to a project at creation."""

    def test_create_project_admin_with_project_creates_membership(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "pa@test.com",
                "display_name": "Project Admin",
                "role": "project_admin",
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "project_admin"
        memberships = data["project_memberships"]
        assert any(
            m["role"] == "project_admin" and m["project_id"] == str(db_project.id)
            for m in memberships
        )

    def test_create_project_admin_without_project_rejected(
        self, client: TestClient, admin_token: str
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "pa-noproj@test.com",
                "display_name": "No Project",
                "role": "project_admin",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_create_standard_with_project_rejected(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "std-proj@test.com",
                "display_name": "Standard With Project",
                "role": "standard",
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_create_project_admin_nonexistent_project(
        self, client: TestClient, admin_token: str, fake_uuid: object
    ) -> None:
        response = client.post(
            "/api/admin/users",
            json={
                "email": "pa-ghost@test.com",
                "display_name": "Ghost Project",
                "role": "project_admin",
                "project_id": str(fake_uuid),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    def test_multiple_project_admins_same_project(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        """Many-to-many: a project may have several project_admins (no uniqueness error)."""
        for email in ("pa-a@test.com", "pa-b@test.com"):
            response = client.post(
                "/api/admin/users",
                json={
                    "email": email,
                    "display_name": email,
                    "role": "project_admin",
                    "project_id": str(db_project.id),
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert response.status_code == 200


class TestAdminUserUpdate:
    """Story 15.5 — edit users with platform-admin immutability and role-flip rules."""

    def _admin_id(self, client: TestClient, admin_token: str) -> str:
        users = client.get(
            "/api/admin/users", headers={"Authorization": f"Bearer {admin_token}"}
        ).json()
        return next(u["id"] for u in users if u["role"] == "admin")

    def test_update_user_valid(self, client: TestClient, admin_token: str, db_user: User) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": "Renamed User",
                "role": "standard",
                "timezone": "Asia/Ho_Chi_Minh",
                "conversation_language": "fr",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Renamed User"
        assert data["timezone"] == "Asia/Ho_Chi_Minh"
        assert data["conversation_language"] == "fr"
        assert "created_at" in data

    def test_update_nonexistent_user_returns_404(
        self, client: TestClient, admin_token: str, fake_uuid: object
    ) -> None:
        response = client.put(
            f"/api/admin/users/{fake_uuid}",
            json={
                "display_name": "Nobody",
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    def test_update_user_invalid_timezone(
        self, client: TestClient, admin_token: str, db_user: User
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": "User",
                "role": "standard",
                "timezone": "Not/AZone",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_update_user_invalid_language(
        self, client: TestClient, admin_token: str, db_user: User
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": "User",
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "xx",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_update_user_promote_to_admin_rejected(
        self, client: TestClient, admin_token: str, db_user: User
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": "User",
                "role": "admin",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_cannot_edit_platform_admin(self, client: TestClient, admin_token: str) -> None:
        admin_id = self._admin_id(client, admin_token)
        response = client.put(
            f"/api/admin/users/{admin_id}",
            json={
                "display_name": "Hacked Admin",
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 403

    def test_cannot_delete_platform_admin(self, client: TestClient, admin_token: str) -> None:
        admin_id = self._admin_id(client, admin_token)
        response = client.delete(
            f"/api/admin/users/{admin_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 403

    def test_admin_cannot_deactivate_self(self, client: TestClient, admin_token: str) -> None:
        admin_id = self._admin_id(client, admin_token)
        response = client.put(
            f"/api/admin/users/{admin_id}",
            json={
                "display_name": "Admin",
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": False,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 403

    def test_non_admin_cannot_update_user(
        self, client: TestClient, user_token: str, db_user: User
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": "X",
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_non_admin_cannot_delete_user(
        self, client: TestClient, user_token: str, db_user: User
    ) -> None:
        response = client.delete(
            f"/api/admin/users/{db_user.id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestAdminUserUpdateProjectAdmin:
    def test_edit_project_admin_reassign_project(
        self,
        client: TestClient,
        admin_token: str,
        db_user: User,
        db_project: Project,
        db_session: Session,
    ) -> None:
        # Create a second project
        proj_b = Project(
            name="Project B",
            description="Second project",
            confluence_base_url="https://confluence.example.com",
            enabled_providers=["openai"],
        )
        db_session.add(proj_b)
        db_session.commit()
        db_session.refresh(proj_b)
        proj_b_id = str(proj_b.id)

        # Promote to project_admin for Project A
        promote = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": db_user.display_name,
                "role": "project_admin",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert promote.status_code == 200

        # Now reassign/add Project B using project_id (legacy semantics)
        reassign = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": db_user.display_name,
                "role": "project_admin",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
                "project_id": proj_b_id,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert reassign.status_code == 200
        data = reassign.json()
        assert data["role"] == "project_admin"
        memberships = data["project_memberships"]

        # AC2/16-13 semantics: Keep A, add B
        assert any(
            m["project_id"] == str(db_project.id) and m["role"] == "project_admin"
            for m in memberships
        )
        assert any(
            m["project_id"] == proj_b_id and m["role"] == "project_admin" for m in memberships
        )

    def test_promote_standard_to_project_admin_creates_membership(
        self, client: TestClient, admin_token: str, db_user: User, db_project: Project
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": db_user.display_name,
                "role": "project_admin",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "project_admin"
        assert any(
            m["role"] == "project_admin" and m["project_id"] == str(db_project.id)
            for m in data["project_memberships"]
        )

    def test_promote_to_project_admin_without_project_rejected(
        self, client: TestClient, admin_token: str, db_user: User
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": db_user.display_name,
                "role": "project_admin",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_demote_project_admin_to_standard_removes_membership(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        created = client.post(
            "/api/admin/users",
            json={
                "email": "demote-me@test.com",
                "display_name": "Demote Me",
                "role": "project_admin",
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert created.status_code == 200
        user_id = created.json()["id"]

        demoted = client.put(
            f"/api/admin/users/{user_id}",
            json={
                "display_name": "Demote Me",
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert demoted.status_code == 200
        data = demoted.json()
        assert data["role"] == "standard"
        assert not any(m["role"] == "project_admin" for m in data["project_memberships"])

    def test_update_standard_with_project_id_rejected(
        self, client: TestClient, admin_token: str, db_user: User, db_project: Project
    ) -> None:
        response = client.put(
            f"/api/admin/users/{db_user.id}",
            json={
                "display_name": db_user.display_name,
                "role": "standard",
                "timezone": "UTC",
                "conversation_language": "en",
                "is_active": True,
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422


class TestAdminUserList:
    def test_list_users(self, client: TestClient, admin_token: str) -> None:
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_non_admin_cannot_list_users(self, client: TestClient, user_token: str) -> None:
        response = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403

    def test_list_users_includes_project_admin_membership(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        """list_users eager-loads memberships and exposes project_name (Story 15.4)."""
        create = client.post(
            "/api/admin/users",
            json={
                "email": "pa-list@test.com",
                "display_name": "PA List",
                "role": "project_admin",
                "project_id": str(db_project.id),
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert create.status_code == 200

        listing = client.get(
            "/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert listing.status_code == 200
        pa = next(u for u in listing.json() if u["email"] == "pa-list@test.com")
        assert any(
            m["role"] == "project_admin" and m["project_name"] == db_project.name
            for m in pa["project_memberships"]
        )
