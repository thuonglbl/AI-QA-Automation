"""Tests for the Azure SSO user-login router (mock-IdP mode).

The test app has no Azure config, so the SSO router runs in its built-in MOCK
IdP mode — no Microsoft, no network. These tests exercise the full round-trip:
login -> mock authorize form -> callback -> app session cookie, plus the
existing-user-only boundary of story 23.2 (no-match => not-provisioned, no user
created). First-login auto-provisioning is story 23.3.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.service import (
    ADMIN_ROLE,
    PROJECT_ADMIN_ROLE,
    STANDARD_ROLE,
    get_user_by_email,
)
from ai_qa.db.models import Project, ProjectMembership, User


@pytest.fixture(autouse=True)
def _force_mock_idp(client: TestClient) -> None:
    """Ensure the SSO router runs in mock-IdP mode for these tests."""
    settings = client.fastapi_app.state.settings  # type: ignore[attr-defined]
    settings.azure_sso_tenant_id = ""
    settings.azure_sso_client_id = ""
    settings.azure_sso_client_secret = ""
    settings.azure_sso_allowed_email_domain = ""
    settings.azure_sso_enabled = False
    settings.azure_sso_auto_provision = False


def _start_login(client: TestClient) -> str:
    """Drive GET /auth/sso/login and return the issued mock ``state``."""
    resp = client.get("/auth/sso/login", follow_redirects=False)
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/auth/sso/authorize")
    state = parse_qs(urlparse(location).query)["state"][0]
    assert state
    return state


def test_login_redirects_to_mock_authorize(client: TestClient) -> None:
    state = _start_login(client)
    assert state


def test_authorize_renders_single_button_form(client: TestClient) -> None:
    state = _start_login(client)
    resp = client.get(f"/auth/sso/authorize?state={state}")
    assert resp.status_code == 200
    body = resp.text
    assert 'data-testid="sso-form"' in body
    assert 'name="email"' in body
    # No password field — SSO-only.
    assert 'type="password"' not in body


def test_callback_existing_user_sets_session_cookie(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user = user_factory("sso.user@example.com", STANDARD_ROLE)
    state = _start_login(client)

    resp = client.post(
        "/auth/sso/callback",
        data={"state": state, "email": user.email},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert "aiqa_session" in resp.headers.get("set-cookie", "")

    # The session cookie now authenticates /auth/me.
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email


def test_callback_unprovisioned_user_is_rejected_and_creates_nothing(
    client: TestClient, db_session: Session
) -> None:
    state = _start_login(client)
    resp = client.post(
        "/auth/sso/callback",
        data={"state": state, "email": "stranger@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?sso_error=not_provisioned"
    assert "aiqa_session" not in resp.headers.get("set-cookie", "")
    # No user was auto-created in 23.2 (provisioning is 23.3).
    assert get_user_by_email(db_session, "stranger@example.com") is None


def test_callback_inactive_user_is_rejected(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user = user_factory("disabled@example.com", STANDARD_ROLE, active=False)
    state = _start_login(client)
    resp = client.post(
        "/auth/sso/callback",
        data={"state": state, "email": user.email},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?sso_error=not_provisioned"
    assert "aiqa_session" not in resp.headers.get("set-cookie", "")


def test_callback_unknown_state_is_rejected(client: TestClient) -> None:
    resp = client.post(
        "/auth/sso/callback",
        data={"state": "not-a-real-state", "email": "x@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?sso_error=state_mismatch"


def test_callback_enforces_allowed_email_domain(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    # Tighten the allowed domain on the live settings instance.
    client.fastapi_app.state.settings.azure_sso_allowed_email_domain = "corp.vn"  # type: ignore[attr-defined]
    user_factory("person@example.com", STANDARD_ROLE)
    state = _start_login(client)
    resp = client.post(
        "/auth/sso/callback",
        data={"state": state, "email": "person@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/?sso_error=domain_not_allowed"


# --- story 23.3: auto-provisioning + Azure app-role mapping -----------------


def _enable_provisioning(client: TestClient, *, domain: str = "") -> None:
    settings = client.fastapi_app.state.settings  # type: ignore[attr-defined]
    settings.azure_sso_enabled = True
    settings.azure_sso_auto_provision = True
    settings.azure_sso_allowed_email_domain = domain


def _mock_login(client: TestClient, email: str, roles: str = "") -> Response:
    state = _start_login(client)
    data = {"state": state, "email": email}
    if roles:
        data["roles"] = roles
    return client.post("/auth/sso/callback", data=data, follow_redirects=False)


def _session_roles(client: TestClient, response: Response) -> list[str]:
    token = response.cookies.get("aiqa_session")
    assert token
    session = SessionManager(client.fastapi_app.state.settings).decode_session(token)  # type: ignore[attr-defined]
    assert session is not None
    return session.roles


def test_provision_creates_identity_only_user(client: TestClient, db_session: Session) -> None:
    _enable_provisioning(client)
    resp = _mock_login(client, "newbie@example.com", roles="user")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"

    user = get_user_by_email(db_session, "newbie@example.com")
    assert user is not None
    assert user.role == STANDARD_ROLE
    assert user.azure_oid == "mock-newbie"
    assert user.is_active


def test_provision_off_rejects_and_creates_nothing(client: TestClient, db_session: Session) -> None:
    # enabled but auto_provision off => no provisioning.
    client.fastapi_app.state.settings.azure_sso_enabled = True  # type: ignore[attr-defined]
    resp = _mock_login(client, "blocked@example.com")
    assert resp.headers["location"] == "/?sso_error=not_provisioned"
    assert get_user_by_email(db_session, "blocked@example.com") is None


def test_provision_azure_admin_role_bootstraps_admin(
    client: TestClient, db_session: Session
) -> None:
    _enable_provisioning(client)
    resp = _mock_login(client, "boss@example.com", roles="admin")
    assert resp.headers["location"] == "/"
    user = get_user_by_email(db_session, "boss@example.com")
    assert user is not None
    assert user.role == ADMIN_ROLE
    assert ADMIN_ROLE in _session_roles(client, resp)


def test_provision_multi_role_session_carries_full_set(
    client: TestClient, db_session: Session
) -> None:
    _enable_provisioning(client)
    resp = _mock_login(client, "multi@example.com", roles="project-admin user")
    user = get_user_by_email(db_session, "multi@example.com")
    assert user is not None
    assert user.role == PROJECT_ADMIN_ROLE  # primary = highest privilege
    assert set(_session_roles(client, resp)) == {PROJECT_ADMIN_ROLE, STANDARD_ROLE}


def test_provision_disallowed_domain_rejected(client: TestClient, db_session: Session) -> None:
    _enable_provisioning(client, domain="corp.vn")
    resp = _mock_login(client, "outsider@example.com", roles="user")
    assert resp.headers["location"] == "/?sso_error=domain_not_allowed"
    assert get_user_by_email(db_session, "outsider@example.com") is None


def test_relogin_refreshes_role_but_keeps_memberships_and_timezone(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    # A standard user with a project_admin membership (pre-assigned by an admin).
    user = user_factory("pa@example.com", STANDARD_ROLE)
    user.timezone = "Asia/Ho_Chi_Minh"
    project = Project(name="PA Project", enabled_providers=["openai"])
    db_session.add(project)
    db_session.commit()
    db_session.add(
        ProjectMembership(project_id=project.id, user_id=user.id, role=PROJECT_ADMIN_ROLE)
    )
    db_session.commit()

    # Log in with NO Azure project-admin claim — membership must confer the role.
    resp = _mock_login(client, "pa@example.com", roles="user")
    assert resp.headers["location"] == "/"
    assert PROJECT_ADMIN_ROLE in _session_roles(client, resp)

    db_session.expire_all()
    refreshed = get_user_by_email(db_session, "pa@example.com")
    assert refreshed is not None
    assert refreshed.role == PROJECT_ADMIN_ROLE  # conferred, not downgraded
    assert refreshed.timezone == "Asia/Ho_Chi_Minh"  # not clobbered by re-sync
    memberships = (
        db_session.query(ProjectMembership).filter(ProjectMembership.user_id == user.id).all()
    )
    assert len(memberships) == 1  # membership preserved


# --- story 23.4: roles + avatar on the auth payloads ------------------------


def test_status_includes_roles_after_sso_login(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory("statususer@example.com", STANDARD_ROLE)
    _mock_login(client, "statususer@example.com", roles="user")
    status = client.get("/auth/status").json()
    assert status["authenticated"] is True
    assert status["roles"] == [STANDARD_ROLE]
    assert status["avatar_url"] is None  # no Azure photo => initials fallback


def test_avatar_route_404_without_photo(
    client: TestClient, user_factory: Callable[..., User]
) -> None:
    user_factory("nopic@example.com", STANDARD_ROLE)
    _mock_login(client, "nopic@example.com")
    resp = client.get("/auth/me/avatar")
    assert resp.status_code == 404


def test_avatar_route_serves_stored_photo(
    client: TestClient, db_session: Session, user_factory: Callable[..., User]
) -> None:
    user = user_factory("haspic@example.com", STANDARD_ROLE)
    # 1x1 transparent PNG, base64.
    png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    user.avatar = f"data:image/png;base64,{png_b64}"
    db_session.commit()

    _mock_login(client, "haspic@example.com")
    status = client.get("/auth/status").json()
    assert status["avatar_url"] == "/auth/me/avatar"

    resp = client.get("/auth/me/avatar")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert len(resp.content) > 0
