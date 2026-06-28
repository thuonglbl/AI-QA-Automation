"""Authentication domain services backed by PostgreSQL."""

from collections.abc import Iterable

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_qa.db.models import User

STANDARD_ROLE = "standard"
ADMIN_ROLE = "admin"
# Per-project administrator: a platform-level role (User.role) whose authority is scoped
# to the projects where the user holds a ProjectMembership(role="project_admin").
PROJECT_ADMIN_ROLE = "project_admin"
_email_adapter = TypeAdapter(EmailStr)

# Azure App Role *value* string -> platform role constant (Epic 23, story 23.3).
# Driven by a constant dict so a renamed Azure role is a one-line change. Lower-cased
# on lookup; underscore/hyphen variants of "project admin" both accepted defensively.
AZURE_APP_ROLE_TO_PLATFORM: dict[str, str] = {
    "admin": ADMIN_ROLE,
    "project-admin": PROJECT_ADMIN_ROLE,
    "project_admin": PROJECT_ADMIN_ROLE,
    "user": STANDARD_ROLE,
}
# Highest-privilege wins when collapsing a multi-role set to the single User.role primary.
_ROLE_PRIORITY: dict[str, int] = {ADMIN_ROLE: 3, PROJECT_ADMIN_ROLE: 2, STANDARD_ROLE: 1}


def map_app_roles(roles_claim: Iterable[str] | None) -> set[str]:
    """Map Azure app-role values to the platform role set.

    Unknown/empty input maps to ``{STANDARD_ROLE}`` — never crashes, never empty.
    """
    if not roles_claim:
        return {STANDARD_ROLE}
    mapped = {
        AZURE_APP_ROLE_TO_PLATFORM[value]
        for raw in roles_claim
        if isinstance(raw, str) and (value := raw.strip().lower()) in AZURE_APP_ROLE_TO_PLATFORM
    }
    return mapped or {STANDARD_ROLE}


def primary_role(roles: set[str]) -> str:
    """Collapse a role set to a single primary: admin > project_admin > standard."""
    if not roles:
        return STANDARD_ROLE
    return max(roles, key=lambda role: _ROLE_PRIORITY.get(role, 0))


def normalize_email(email: str) -> str:
    """Normalize email addresses for unique storage and lookup."""
    return email.strip().lower()


def get_user_by_email(session: Session, email: str) -> User | None:
    """Return a user by normalized email, if present."""
    statement = select(User).where(User.email == normalize_email(email))
    return session.execute(statement).scalar_one_or_none()


class InvalidBootstrapInputError(ValueError):
    """Raised when admin bootstrap input is unsafe or incomplete."""


def bootstrap_admin(
    session: Session,
    email: str,
    display_name: str,
) -> User:
    """Create or update an admin user idempotently for operator bootstrap."""
    normalized_email = normalize_email(email)
    cleaned_name = display_name.strip()
    if not normalized_email or not cleaned_name:
        raise InvalidBootstrapInputError("Email and display name are required")
    try:
        _email_adapter.validate_python(normalized_email)
    except ValidationError as exc:
        raise InvalidBootstrapInputError("A valid email address is required") from exc

    user = get_user_by_email(session, normalized_email)
    if user is None:
        user = User(
            email=normalized_email,
            display_name=cleaned_name,
            role=ADMIN_ROLE,
            is_active=True,
        )
        session.add(user)
    else:
        user.display_name = cleaned_name
        user.role = ADMIN_ROLE
        user.is_active = True

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise InvalidBootstrapInputError("Admin bootstrap could not be completed") from exc
    session.refresh(user)
    return user
