"""Test-account credential management API (user-scoped).

Users can store their own dedicated test-account credentials (username, password, TOTP)
for an (environment, role) pair in projects they belong to. These are encrypted at rest
with user secrets and never returned in plaintext.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.api.projects import require_project_member_or_admin
from ai_qa.db.models import TestAccountCredential, User
from ai_qa.sessions import service as session_service

logger = logging.getLogger(__name__)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

router = APIRouter(prefix="/projects", tags=["test-credentials"])


class TestAccountCredentialCreate(BaseModel):
    environment: str
    role: str
    username: str
    password: str
    totp_secret: str | None = None


class TestAccountCredentialUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    totp_secret: str | None = None


class TestAccountCredentialResponse(BaseModel):
    id: UUID
    environment: str
    role: str
    username: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/{project_id}/test-credentials", response_model=list[TestAccountCredentialResponse])
async def list_test_credentials(
    project_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> list[TestAccountCredentialResponse]:
    """List test credentials for the project that belong to the current user."""
    project = await require_project_member_or_admin(project_id, current_user, db)

    stmt = select(TestAccountCredential).where(
        TestAccountCredential.project_id == project.id,
        TestAccountCredential.user_id == current_user.id,
    )
    credentials = db.scalars(stmt).all()

    return [TestAccountCredentialResponse.model_validate(c) for c in credentials]


@router.put("/{project_id}/test-credentials", response_model=TestAccountCredentialResponse)
async def upsert_test_credential(
    project_id: UUID,
    payload: TestAccountCredentialCreate,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> TestAccountCredentialResponse:
    """Create or update a test credential for an (environment, role) pair for the current user."""
    # Ensure project exists and user is a member
    await require_project_member_or_admin(project_id, current_user, db)

    stmt = select(TestAccountCredential).where(
        TestAccountCredential.user_id == current_user.id,
        TestAccountCredential.project_id == project_id,
        TestAccountCredential.environment == payload.environment,
        TestAccountCredential.role == payload.role,
    )
    credential = db.scalar(stmt)

    if credential:
        credential.username = payload.username
        credential.password = payload.password
        credential.totp_secret = payload.totp_secret
    else:
        credential = TestAccountCredential(
            user_id=current_user.id,
            project_id=project_id,
            environment=payload.environment,
            role=payload.role,
            username=payload.username,
            password=payload.password,
            totp_secret=payload.totp_secret,
        )
        db.add(credential)

    db.commit()
    db.refresh(credential)

    # The previously captured session (if any) was derived from the OLD credential and
    # may be stale/expired. Drop it so the UI doesn't keep showing "Session expired" after
    # an update and the next run logs in fresh with the new credential.
    session_service.delete_captured_session(
        db,
        user_id=current_user.id,
        project_id=project_id,
        environment=payload.environment,
        role=payload.role,
    )

    return TestAccountCredentialResponse.model_validate(credential)


@router.delete(
    "/{project_id}/test-credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_test_credential(
    project_id: UUID,
    credential_id: UUID,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> None:
    """Delete a test credential for the current user."""
    stmt = select(TestAccountCredential).where(
        TestAccountCredential.id == credential_id,
        TestAccountCredential.user_id == current_user.id,
        TestAccountCredential.project_id == project_id,
    )
    credential = db.scalar(stmt)

    if not credential:
        raise HTTPException(status_code=404, detail="Test credential not found")

    # A credential and its captured session are two halves of one login. Capture the
    # (environment, role) before deleting so we can also drop any cached session —
    # otherwise the UI shows a "logged in" session with no backing credential.
    environment = credential.environment
    role = credential.role

    db.delete(credential)
    db.commit()

    session_service.delete_captured_session(
        db,
        user_id=current_user.id,
        project_id=project_id,
        environment=environment,
        role=role,
    )
