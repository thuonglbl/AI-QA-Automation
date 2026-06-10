"""API tests for admin project management endpoints."""

import pytest

from ai_qa.api.auth.rbac import ADMIN_ROLE


@pytest.fixture
def admin_user(db_session, user_factory):
    user = user_factory(role=ADMIN_ROLE)
    db_session.add(user)
    db_session.commit()
    return user


class TestAdminProjectCreate:
    @pytest.mark.asyncio
    async def test_create_project_valid_data(self, client, admin_token):
        response = await client.post(
            "/admin/projects",
            json={
                "name": "Test Project",
                "description": "A test project",
                "confluence_base_url": "https://confluence.example.com",
                "enabled_providers": ["openai"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Project"

    @pytest.mark.asyncio
    async def test_create_project_duplicate_name(self, client, admin_token, db_project):
        response = await client.post(
            "/admin/projects",
            json={
                "name": db_project.name,
                "description": "Duplicate",
                "enabled_providers": ["openai"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_project_no_providers_fails(self, client, admin_token):
        response = await client.post(
            "/admin/projects",
            json={
                "name": "No Provider",
                "confluence_base_url": "https://example.com",
                "enabled_providers": [],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_project_no_links_fails(self, client, admin_token):
        response = await client.post(
            "/admin/projects",
            json={"name": "No Links", "enabled_providers": ["openai"]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_project(self, client, user_token):
        response = await client.post(
            "/admin/projects",
            json={
                "name": "Unauthorized Project",
                "description": "Should fail",
                "confluence_base_url": "https://example.com",
                "enabled_providers": ["openai"],
            },
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert response.status_code == 403


class TestAdminProjectUpdate:
    @pytest.mark.asyncio
    async def test_update_project_details(self, client, admin_token, db_project):
        response = await client.put(
            f"/admin/projects/{db_project.id}",
            json={
                "name": "Updated Name",
                "description": "Updated",
                "confluence_base_url": "https://example.com",
                "enabled_providers": ["anthropic"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_nonexistent_project(self, client, admin_token, fake_uuid):
        response = await client.put(
            f"/admin/projects/{fake_uuid}",
            json={
                "name": "Ghost",
                "description": None,
                "confluence_base_url": "https://example.com",
                "enabled_providers": ["openai"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404


class TestAdminProjectDelete:
    @pytest.mark.asyncio
    async def test_delete_project(self, client, admin_token, db_project):
        response = await client.delete(
            f"/admin/projects/{db_project.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_nonexistent_project(self, client, admin_token, fake_uuid):
        response = await client.delete(
            f"/admin/projects/{fake_uuid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404
