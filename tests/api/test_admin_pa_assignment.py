"""Story 23.5: multi-project project-admin assignment + admin global authority.

Drives ``PUT /api/admin/users/{id}`` with the new ``project_ids`` set and asserts
set-reconciliation (add/remove only the targeted user's project_admin rows), plus
the admin backdoor on a per-project project-admin route.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ai_qa.auth.service import PROJECT_ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.models import Project, ProjectMembership, User


def _project(db: Session, name: str) -> Project:
    project = Project(name=name, enabled_providers=["openai"])
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _pa_project_ids(db: Session, user_id: uuid.UUID) -> set[uuid.UUID]:
    rows = (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.user_id == user_id,
            ProjectMembership.role == PROJECT_ADMIN_ROLE,
        )
        .all()
    )
    return {m.project_id for m in rows}


def _update(client: TestClient, token: str, user_id: uuid.UUID, body: dict[str, Any]):
    return client.put(
        f"/api/admin/users/{user_id}",
        json=body,
        headers={"Authorization": f"Bearer {token}"},
    )


def _pa_body(name: str, project_ids: list[uuid.UUID]) -> dict[str, object]:
    return {
        "display_name": name,
        "role": "project_admin",
        "timezone": "UTC",
        "conversation_language": "en",
        "is_active": True,
        "project_ids": [str(pid) for pid in project_ids],
    }


def test_project_ids_reconciles_the_administered_set(
    client: TestClient,
    db_session: Session,
    admin_token: str,
    user_factory: Callable[..., User],
) -> None:
    pa = user_factory("pa@example.com", PROJECT_ADMIN_ROLE)
    a, b, c = _project(db_session, "A"), _project(db_session, "B"), _project(db_session, "C")
    db_session.add(ProjectMembership(project_id=a.id, user_id=pa.id, role=PROJECT_ADMIN_ROLE))
    db_session.commit()

    # {A} -> {A, B}
    resp = _update(client, admin_token, pa.id, _pa_body("PA", [a.id, b.id]))
    assert resp.status_code == 200
    db_session.expire_all()
    assert _pa_project_ids(db_session, pa.id) == {a.id, b.id}

    # {A, B} -> {B, C}: A removed, C added.
    resp = _update(client, admin_token, pa.id, _pa_body("PA", [b.id, c.id]))
    assert resp.status_code == 200
    db_session.expire_all()
    assert _pa_project_ids(db_session, pa.id) == {b.id, c.id}

    # Idempotent: re-sending the same set is a no-op.
    resp = _update(client, admin_token, pa.id, _pa_body("PA", [b.id, c.id]))
    assert resp.status_code == 200
    db_session.expire_all()
    assert _pa_project_ids(db_session, pa.id) == {b.id, c.id}


def test_reconcile_leaves_other_users_and_other_roles_untouched(
    client: TestClient,
    db_session: Session,
    admin_token: str,
    user_factory: Callable[..., User],
) -> None:
    pa = user_factory("pa@example.com", PROJECT_ADMIN_ROLE)
    other = user_factory("other-pa@example.com", PROJECT_ADMIN_ROLE)
    a, b, d = _project(db_session, "A"), _project(db_session, "B"), _project(db_session, "D")
    db_session.add_all(
        [
            ProjectMembership(project_id=a.id, user_id=pa.id, role=PROJECT_ADMIN_ROLE),
            ProjectMembership(project_id=a.id, user_id=other.id, role=PROJECT_ADMIN_ROLE),
            # A plain member row for the SAME user on a different project — must survive.
            ProjectMembership(project_id=d.id, user_id=pa.id, role="member"),
        ]
    )
    db_session.commit()

    resp = _update(client, admin_token, pa.id, _pa_body("PA", [b.id]))
    assert resp.status_code == 200
    db_session.expire_all()

    assert _pa_project_ids(db_session, pa.id) == {b.id}  # A removed
    assert _pa_project_ids(db_session, other.id) == {a.id}  # other user untouched
    member_rows = (
        db_session.query(ProjectMembership)
        .filter(ProjectMembership.user_id == pa.id, ProjectMembership.role == "member")
        .all()
    )
    assert {m.project_id for m in member_rows} == {d.id}  # non-PA row untouched


def test_unknown_project_id_is_rejected(
    client: TestClient,
    db_session: Session,
    admin_token: str,
    user_factory: Callable[..., User],
) -> None:
    pa = user_factory("pa@example.com", PROJECT_ADMIN_ROLE)
    resp = _update(client, admin_token, pa.id, _pa_body("PA", [uuid.uuid4()]))
    assert resp.status_code == 404


def test_empty_project_set_for_project_admin_is_rejected(
    client: TestClient,
    db_session: Session,
    admin_token: str,
    user_factory: Callable[..., User],
) -> None:
    pa = user_factory("pa@example.com", PROJECT_ADMIN_ROLE)
    resp = _update(client, admin_token, pa.id, _pa_body("PA", []))
    assert resp.status_code == 422


def test_standard_user_cannot_receive_project_ids(
    client: TestClient,
    db_session: Session,
    admin_token: str,
    user_factory: Callable[..., User],
) -> None:
    std = user_factory("std@example.com", STANDARD_ROLE)
    project = _project(db_session, "P")
    body = {
        "display_name": "Std",
        "role": "standard",
        "timezone": "UTC",
        "is_active": True,
        "project_ids": [str(project.id)],
    }
    resp = _update(client, admin_token, std.id, body)
    assert resp.status_code == 422


def test_admin_reaches_project_with_no_membership(
    client: TestClient,
    db_session: Session,
    admin_token: str,
    user_factory: Callable[..., User],
) -> None:
    # AC1: a platform admin holds zero ProjectMembership rows yet administers every project.
    project = _project(db_session, "Unmembered Project")
    member = user_factory("m@example.com", STANDARD_ROLE)

    add = client.post(
        f"/api/project-admin/projects/{project.id}/members",
        json={"user_id": str(member.id), "role": "member"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert add.status_code == 200  # backdoor: not 403

    listing = client.get(
        "/api/project-admin/projects",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert listing.status_code == 200
    assert any(p["id"] == str(project.id) for p in listing.json())
