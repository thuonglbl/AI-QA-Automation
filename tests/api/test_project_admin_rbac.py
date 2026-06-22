"""Unit tests for the project-admin authorization dependency + project-admin API (WS-A/B)."""

from collections.abc import Callable

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.api.auth.rbac import require_project_admin_for_project
from ai_qa.auth.service import ADMIN_ROLE, PROJECT_ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.models import Project, ProjectMembership, User


def _project(db: Session, name: str = "P") -> Project:
    project = Project(name=name, enabled_providers=["openai"])
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _make_project_admin(db: Session, user: User, project: Project) -> None:
    db.add(ProjectMembership(project_id=project.id, user_id=user.id, role=PROJECT_ADMIN_ROLE))
    db.commit()


class TestRequireProjectAdminForProject:
    @pytest.mark.asyncio
    async def test_platform_admin_always_allowed(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        admin = user_factory("a@example.com", role=ADMIN_ROLE)
        project = _project(db_session)
        # No membership needed — platform admins are a backdoor.
        result = await require_project_admin_for_project(project.id, admin, db_session)
        assert result is admin

    @pytest.mark.asyncio
    async def test_project_admin_with_membership_allowed(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        padmin = user_factory("pa@example.com", role=PROJECT_ADMIN_ROLE)
        project = _project(db_session)
        _make_project_admin(db_session, padmin, project)
        result = await require_project_admin_for_project(project.id, padmin, db_session)
        assert result is padmin

    @pytest.mark.asyncio
    async def test_project_admin_without_membership_forbidden(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        padmin = user_factory("pa2@example.com", role=PROJECT_ADMIN_ROLE)
        other = _project(db_session, name="Other")
        with pytest.raises(HTTPException) as exc:
            await require_project_admin_for_project(other.id, padmin, db_session)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_standard_member_forbidden(
        self, db_session: Session, user_factory: Callable[..., User]
    ) -> None:
        standard = user_factory("s@example.com", role=STANDARD_ROLE)
        project = _project(db_session)
        db_session.add(ProjectMembership(project_id=project.id, user_id=standard.id, role="member"))
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            await require_project_admin_for_project(project.id, standard, db_session)
        assert exc.value.status_code == 403


_CONFIG = {
    "confluence_base_url": "https://confluence.example.com",
    "enabled_providers": ["openai"],
    "environments": [{"name": "Test 1", "url": "https://t1.app"}],
    "app_roles": ["Admin", "User"],
}


class TestProjectAdminApi:
    def _setup(
        self,
        db: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> tuple[Project, str]:
        padmin = user_factory(role=PROJECT_ADMIN_ROLE)
        project = _project(db, name="Admined")
        _make_project_admin(db, padmin, project)
        return project, token_factory(padmin)

    def test_list_administered_only(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project, token = self._setup(db_session, user_factory, token_factory)
        _project(db_session, name="NotMine")  # a project the padmin does NOT administer
        resp = client.get(
            "/api/project-admin/projects", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        names = {p["name"] for p in resp.json()}
        assert names == {"Admined"}

    def test_platform_admin_lists_all(
        self,
        client: TestClient,
        admin_token: str,
        db_session: Session,
    ) -> None:
        _project(db_session, name="One")
        _project(db_session, name="Two")
        resp = client.get(
            "/api/project-admin/projects", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert resp.status_code == 200
        assert {"One", "Two"} <= {p["name"] for p in resp.json()}

    def test_standard_cannot_list(self, client: TestClient, user_token: str) -> None:
        resp = client.get(
            "/api/project-admin/projects", headers={"Authorization": f"Bearer {user_token}"}
        )
        assert resp.status_code == 403

    def test_config_updates_own_project(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project, token = self._setup(db_session, user_factory, token_factory)
        resp = client.put(
            f"/api/project-admin/projects/{project.id}/config",
            json=_CONFIG,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["confluence_base_url"] == "https://confluence.example.com"
        assert body["app_roles"] == ["Admin", "User"]
        assert body["environments"] == [{"name": "Test 1", "url": "https://t1.app"}]

    def test_config_requires_link_and_provider(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project, token = self._setup(db_session, user_factory, token_factory)
        no_provider = client.put(
            f"/api/project-admin/projects/{project.id}/config",
            json={**_CONFIG, "enabled_providers": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        no_link = client.put(
            f"/api/project-admin/projects/{project.id}/config",
            json={**_CONFIG, "confluence_base_url": None, "jira_base_url": None},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert no_provider.status_code == 422
        assert no_link.status_code == 422

    def test_config_forbidden_on_other_project(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        _, token = self._setup(db_session, user_factory, token_factory)
        other = _project(db_session, name="Other")
        resp = client.put(
            f"/api/project-admin/projects/{other.id}/config",
            json=_CONFIG,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_add_and_remove_member(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project, token = self._setup(db_session, user_factory, token_factory)
        member = user_factory(role=STANDARD_ROLE)
        headers = {"Authorization": f"Bearer {token}"}

        added = client.post(
            f"/api/project-admin/projects/{project.id}/members",
            json={"user_id": str(member.id), "role": "member"},
            headers=headers,
        )
        assert added.status_code == 200
        assert added.json()["user_id"] == str(member.id)

        removed = client.delete(
            f"/api/project-admin/projects/{project.id}/members/{member.id}",
            headers=headers,
        )
        assert removed.status_code == 204

    def test_project_admin_cannot_remove_project_admin(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        padmin = user_factory(role=PROJECT_ADMIN_ROLE)
        project = _project(db_session, name="Admined")
        _make_project_admin(db_session, padmin, project)
        headers = {"Authorization": f"Bearer {token_factory(padmin)}"}

        other = user_factory(role=PROJECT_ADMIN_ROLE)
        _make_project_admin(db_session, other, project)

        # A project_admin can remove neither another project_admin nor themselves.
        other_resp = client.delete(
            f"/api/project-admin/projects/{project.id}/members/{other.id}", headers=headers
        )
        self_resp = client.delete(
            f"/api/project-admin/projects/{project.id}/members/{padmin.id}", headers=headers
        )
        assert other_resp.status_code == 403
        assert self_resp.status_code == 403

        # Both project-admin memberships are preserved.
        remaining = (
            db_session.execute(
                select(ProjectMembership).where(ProjectMembership.project_id == project.id)
            )
            .scalars()
            .all()
        )
        assert {m.user_id for m in remaining} == {padmin.id, other.id}

    def test_project_admin_cannot_assign_non_standard_user(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project, token = self._setup(db_session, user_factory, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        for target in (user_factory(role=ADMIN_ROLE), user_factory(role=PROJECT_ADMIN_ROLE)):
            resp = client.post(
                f"/api/project-admin/projects/{project.id}/members",
                json={"user_id": str(target.id), "role": "member"},
                headers=headers,
            )
            assert resp.status_code == 403
            written = db_session.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project.id,
                    ProjectMembership.user_id == target.id,
                )
            ).scalar_one_or_none()
            assert written is None

    def test_project_admin_cannot_downgrade_elevated_member_via_upsert(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        # Inconsistent-but-defended state: a standard global-role user who nevertheless holds
        # an elevated membership. The upsert must not let a project_admin rewrite its role.
        project, token = self._setup(db_session, user_factory, token_factory)
        elevated = user_factory(role=STANDARD_ROLE)
        db_session.add(
            ProjectMembership(project_id=project.id, user_id=elevated.id, role=PROJECT_ADMIN_ROLE)
        )
        db_session.commit()

        resp = client.post(
            f"/api/project-admin/projects/{project.id}/members",
            json={"user_id": str(elevated.id), "role": "member"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        kept = db_session.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == project.id,
                ProjectMembership.user_id == elevated.id,
            )
        ).scalar_one()
        db_session.refresh(kept)
        assert kept.role == PROJECT_ADMIN_ROLE

    def test_project_admin_cannot_assign_elevated_membership_role(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project, token = self._setup(db_session, user_factory, token_factory)
        standard = user_factory(role=STANDARD_ROLE)
        resp = client.post(
            f"/api/project-admin/projects/{project.id}/members",
            json={"user_id": str(standard.id), "role": "project_admin"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_platform_admin_can_remove_project_admin(
        self,
        client: TestClient,
        admin_token: str,
        db_session: Session,
        user_factory: Callable[..., User],
    ) -> None:
        project = _project(db_session, name="Admined")
        padmin = user_factory(role=PROJECT_ADMIN_ROLE)
        _make_project_admin(db_session, padmin, project)
        resp = client.delete(
            f"/api/project-admin/projects/{project.id}/members/{padmin.id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 204

    def test_member_management_forbidden_for_standard(
        self,
        client: TestClient,
        user_token: str,
        db_session: Session,
        user_factory: Callable[..., User],
    ) -> None:
        project = _project(db_session, name="X")
        member = user_factory(role=STANDARD_ROLE)
        resp = client.post(
            f"/api/project-admin/projects/{project.id}/members",
            json={"user_id": str(member.id), "role": "member"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403


def _configured_project(db: Session, login_type: str = "SSO") -> Project:
    project = Project(
        name=f"Acct {login_type}",
        enabled_providers=["openai"],
        environments=[{"name": "Test 1", "url": "https://t1.app"}],
        app_roles=["Admin", "User"],
        login_type=login_type,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


class TestProjectAccounts:
    def _admin_token(
        self,
        db: Session,
        project: Project,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> str:
        padmin = user_factory(role=PROJECT_ADMIN_ROLE)
        _make_project_admin(db, padmin, project)
        return token_factory(padmin)

    def test_login_type_round_trips_via_config(
        self,
        client: TestClient,
        admin_token: str,
        db_session: Session,
    ) -> None:
        project = _configured_project(db_session, login_type="SSO")
        resp = client.put(
            f"/api/project-admin/projects/{project.id}/config",
            json={**_CONFIG, "login_type": "PASSWORD"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["login_type"] == "PASSWORD"

    def test_sso_account_stores_no_password(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project = _configured_project(db_session, login_type="SSO")
        token = self._admin_token(db_session, project, user_factory, token_factory)
        resp = client.post(
            f"/api/project-admin/projects/{project.id}/accounts",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "login_identifier": "qa-admin@corp",
                "password": "should-be-ignored",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["login_identifier"] == "qa-admin@corp"
        assert body["has_password"] is False  # SSO never stores a password
        assert "password" not in body
        assert "should-be-ignored" not in resp.text

    def test_password_account_requires_and_hides_password(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project = _configured_project(db_session, login_type="PASSWORD")
        token = self._admin_token(db_session, project, user_factory, token_factory)
        headers = {"Authorization": f"Bearer {token}"}

        # Missing password → rejected for a PASSWORD project.
        missing = client.post(
            f"/api/project-admin/projects/{project.id}/accounts",
            json={"environment": "Test 1", "role": "Admin", "login_identifier": "u@corp"},
            headers=headers,
        )
        assert missing.status_code == 422

        ok = client.post(
            f"/api/project-admin/projects/{project.id}/accounts",
            json={
                "environment": "Test 1",
                "role": "Admin",
                "login_identifier": "u@corp",
                "password": "s3cr3t-pass",
            },
            headers=headers,
        )
        assert ok.status_code == 200
        assert ok.json()["has_password"] is True
        assert "s3cr3t-pass" not in ok.text  # password never returned

        # Listed accounts also never leak the password.
        listed = client.get(f"/api/project-admin/projects/{project.id}/accounts", headers=headers)
        assert listed.status_code == 200
        assert "s3cr3t-pass" not in listed.text
        assert listed.json()[0]["has_password"] is True

    def test_account_rejects_unknown_env_or_role(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project = _configured_project(db_session, login_type="SSO")
        token = self._admin_token(db_session, project, user_factory, token_factory)
        resp = client.post(
            f"/api/project-admin/projects/{project.id}/accounts",
            json={"environment": "Ghost", "role": "Admin", "login_identifier": "x@y"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    def test_account_delete(
        self,
        client: TestClient,
        db_session: Session,
        user_factory: Callable[..., User],
        token_factory: Callable[[User], str],
    ) -> None:
        project = _configured_project(db_session, login_type="SSO")
        token = self._admin_token(db_session, project, user_factory, token_factory)
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post(
            f"/api/project-admin/projects/{project.id}/accounts",
            json={"environment": "Test 1", "role": "User", "login_identifier": "u@corp"},
            headers=headers,
        ).json()
        deleted = client.delete(
            f"/api/project-admin/projects/{project.id}/accounts/{created['id']}",
            headers=headers,
        )
        assert deleted.status_code == 204
        assert (
            client.get(f"/api/project-admin/projects/{project.id}/accounts", headers=headers).json()
            == []
        )

    def test_accounts_forbidden_for_standard(
        self, client: TestClient, user_token: str, db_session: Session
    ) -> None:
        project = _configured_project(db_session)
        resp = client.get(
            f"/api/project-admin/projects/{project.id}/accounts",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403
