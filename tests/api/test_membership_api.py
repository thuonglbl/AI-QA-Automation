"""API tests for project membership endpoints."""

import pytest


class TestAdminMembershipAssign:
    @pytest.mark.asyncio
    async def test_assign_member_to_project(self, client, admin_token, db_project, db_user):
        response = await client.post(
            f"/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(db_user.id), "role": "member"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "member"

    @pytest.mark.asyncio
    async def test_assign_owner_role(self, client, admin_token, db_project, db_user2):
        response = await client.post(
            f"/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(db_user2.id), "role": "owner"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "owner"

    @pytest.mark.asyncio
    async def test_assign_to_nonexistent_project(self, client, admin_token, fake_uuid, db_user):
        response = await client.post(
            f"/admin/projects/{fake_uuid}/memberships",
            json={"user_id": str(db_user.id), "role": "member"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_assign_nonexistent_user(self, client, admin_token, db_project, fake_uuid):
        response = await client.post(
            f"/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(fake_uuid), "role": "member"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestAdminMembershipRemove:
    @pytest.mark.asyncio
    async def test_remove_membership(self, client, admin_token, db_project, db_membership):
        response = await client.delete(
            f"/admin/projects/{db_project.id}/memberships/{db_membership.user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_remove_nonexistent_membership(self, client, admin_token, db_project, fake_uuid):
        response = await client.delete(
            f"/admin/projects/{db_project.id}/memberships/{fake_uuid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_non_admin_cannot_assign_membership(
        self, client, user_token, db_project, db_user
    ):
        response = await client.post(
            f"/admin/projects/{db_project.id}/memberships",
            json={"user_id": str(db_user.id), "role": "member"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
