"""API tests for admin project management endpoints."""

from fastapi.testclient import TestClient

from ai_qa.db.models import Project


class TestAdminProjectCreate:
    def test_create_project_valid_data(self, client: TestClient, admin_token: str) -> None:
        response = client.post(
            "/api/admin/projects",
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

    def test_create_project_with_environments(self, client: TestClient, admin_token: str) -> None:
        """Environments persist; blank rows are dropped, valid ones are trimmed."""
        response = client.post(
            "/api/admin/projects",
            json={
                "name": "Env Project",
                "confluence_base_url": "https://confluence.example.com",
                "enabled_providers": ["openai"],
                "environments": [
                    {"name": "  Test 1 ", "url": " https://test1.app "},
                    {"name": "Production", "url": "https://app.example.com"},
                    {"name": "", "url": ""},  # blank → dropped
                    {"name": "Staging", "url": ""},  # incomplete → dropped
                ],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        envs = response.json()["environments"]
        assert envs == [
            {"name": "Test 1", "url": "https://test1.app"},
            {"name": "Production", "url": "https://app.example.com"},
        ]

    def test_create_project_duplicate_environment_name_fails(
        self, client: TestClient, admin_token: str
    ) -> None:
        """Two environments with the same (case-insensitive) name are rejected."""
        response = client.post(
            "/api/admin/projects",
            json={
                "name": "Dup Env Project",
                "confluence_base_url": "https://confluence.example.com",
                "enabled_providers": ["openai"],
                "environments": [
                    {"name": "Test", "url": "https://a.app"},
                    {"name": "test", "url": "https://b.app"},
                ],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 422

    def test_create_project_with_app_roles(self, client: TestClient, admin_token: str) -> None:
        """app_roles persist; trimmed, blanks dropped, case-insensitive dups rejected."""
        ok = client.post(
            "/api/admin/projects",
            json={
                "name": "Roles Project",
                "confluence_base_url": "https://confluence.example.com",
                "enabled_providers": ["openai"],
                "app_roles": ["  Admin ", "User", ""],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert ok.status_code == 200
        assert ok.json()["app_roles"] == ["Admin", "User"]

        dup = client.post(
            "/api/admin/projects",
            json={
                "name": "Dup Roles Project",
                "confluence_base_url": "https://confluence.example.com",
                "enabled_providers": ["openai"],
                "app_roles": ["Admin", "admin"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert dup.status_code == 422

    def test_create_project_duplicate_name(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        response = client.post(
            "/api/admin/projects",
            json={
                "name": db_project.name,
                "description": "Duplicate",
                "confluence_base_url": "https://confluence.example.com",
                "enabled_providers": ["openai"],
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 409
        assert response.json()["detail"] == "Project name already exists"

    def test_create_project_name_only_succeeds(self, client: TestClient, admin_token: str) -> None:
        """Admin now creates a bare project (name [+ description] only); links/providers
        are configured later by the project_admin, so neither is required here."""
        response = client.post(
            "/api/admin/projects",
            json={"name": "Bare Project"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Bare Project"
        assert data["enabled_providers"] == []
        assert data["confluence_base_url"] is None

    def test_confluence_base_url_column_is_nullable(self) -> None:
        """Forward-regression guard for Story 15.1.

        The live-PostgreSQL bug (a residual ``NOT NULL`` on ``confluence_base_url``)
        is invisible to this SQLite suite, which builds the schema from the
        already-nullable ORM model. Assert the model metadata stays nullable so the
        column and migration ``a3d0b6703a7d`` never drift back to ``NOT NULL``.
        """
        assert Project.__table__.c.confluence_base_url.nullable

    def test_non_admin_cannot_create_project(self, client: TestClient, user_token: str) -> None:
        response = client.post(
            "/api/admin/projects",
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
    def test_update_project_details(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        response = client.put(
            f"/api/admin/projects/{db_project.id}",
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

    def test_update_nonexistent_project(
        self, client: TestClient, admin_token: str, fake_uuid: object
    ) -> None:
        response = client.put(
            f"/api/admin/projects/{fake_uuid}",
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
    def test_delete_project(
        self, client: TestClient, admin_token: str, db_project: Project
    ) -> None:
        response = client.delete(
            f"/api/admin/projects/{db_project.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 204

    def test_delete_nonexistent_project(
        self, client: TestClient, admin_token: str, fake_uuid: object
    ) -> None:
        response = client.delete(
            f"/api/admin/projects/{fake_uuid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 404
