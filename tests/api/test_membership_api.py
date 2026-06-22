"""API tests for project membership endpoints."""

from fastapi.testclient import TestClient

from ai_qa.db.models import Project, ProjectMembership, User


class TestAdminMembershipAssign:
    def test_assign_member_to_project(
        self, client: TestClient, admin_token: str, db_project: Project, db_user: User
    ) -> None:
        response = client.post(
            f"/api/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(db_user.id), "role": "member"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"

    def test_assign_owner_role(
        self, client: TestClient, admin_token: str, db_project: Project, db_user2: User
    ) -> None:
        response = client.post(
            f"/api/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(db_user2.id), "role": "owner"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "owner"

    def test_assign_to_nonexistent_project(
        self, client: TestClient, admin_token: str, fake_uuid: object, db_user: User
    ) -> None:
        response = client.post(
            f"/api/admin/projects/{fake_uuid}/memberships",
            json={"user_id": str(db_user.id), "role": "member"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    def test_assign_nonexistent_user(
        self, client: TestClient, admin_token: str, db_project: Project, fake_uuid: object
    ) -> None:
        response = client.post(
            f"/api/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(fake_uuid), "role": "member"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestAdminMembershipRemove:
    def test_remove_membership(
        self,
        client: TestClient,
        admin_token: str,
        db_project: Project,
        db_membership: ProjectMembership,
    ) -> None:
        response = client.delete(
            f"/api/admin/projects/{db_project.id}/memberships/{db_membership.user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

    def test_remove_nonexistent_membership(
        self, client: TestClient, admin_token: str, db_project: Project, fake_uuid: object
    ) -> None:
        response = client.delete(
            f"/api/admin/projects/{db_project.id}/memberships/{fake_uuid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    def test_non_admin_cannot_assign_membership(
        self, client: TestClient, user_token: str, db_project: Project, db_user: User
    ) -> None:
        response = client.post(
            f"/api/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(db_user.id), "role": "member"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
