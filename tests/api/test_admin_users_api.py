"""API tests for admin user management endpoints."""

import pytest


class TestAdminUserCreate:
    @pytest.mark.asyncio
    async def test_create_user_valid(self, client, admin_token):
        response = await client.post(
            "/admin/users",
            json={
                "email": "newuser@test.com",
                "display_name": "New User",
                "initial_password": "StrongPass1!",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@test.com"
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, client, admin_token, db_user):
        response = await client.post(
            "/admin/users",
            json={
                "email": db_user.email,
                "display_name": "Duplicate",
                "initial_password": "StrongPass1!",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_user_weak_password(self, client, admin_token):
        response = await client.post(
            "/admin/users",
            json={
                "email": "weak@test.com",
                "display_name": "Weak Pass",
                "initial_password": "short",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_user(self, client, user_token):
        response = await client.post(
            "/admin/users",
            json={
                "email": "hacker@test.com",
                "display_name": "Hacker",
                "initial_password": "StrongPass1!",
                "role": "standard",
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestAdminUserDelete:
    @pytest.mark.asyncio
    async def test_delete_user(self, client, admin_token, db_user):
        response = await client.delete(
            f"/admin/users/{db_user.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user(self, client, admin_token, fake_uuid):
        response = await client.delete(
            f"/admin/users/{fake_uuid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestAdminUserList:
    @pytest.mark.asyncio
    async def test_list_users(self, client, admin_token):
        response = await client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_non_admin_cannot_list_users(self, client, user_token):
        response = await client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403
