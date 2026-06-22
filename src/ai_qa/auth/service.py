"""Authentication domain services backed by PostgreSQL."""

from dataclasses import dataclass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_qa.auth.password import hash_password, verify_password
from ai_qa.db.models import User

STANDARD_ROLE = "standard"
ADMIN_ROLE = "admin"
# Per-project administrator: a platform-level role (User.role) whose authority is scoped
# to the projects where the user holds a ProjectMembership(role="project_admin").
PROJECT_ADMIN_ROLE = "project_admin"
_MIN_PASSWORD_LENGTH = 8
_email_adapter = TypeAdapter(EmailStr)


class DuplicateUserError(ValueError):
    """Raised when a user email is already registered."""


class InvalidBootstrapInputError(ValueError):
    """Raised when admin bootstrap input is unsafe or incomplete."""


@dataclass(frozen=True)
class AuthFailure:
    """Generic authentication failure marker."""

    reason: str = "Invalid email or password"


def normalize_email(email: str) -> str:
    """Normalize email addresses for unique storage and lookup."""
    return email.strip().lower()


def get_user_by_email(session: Session, email: str) -> User | None:
    """Return a user by normalized email, if present."""
    statement = select(User).where(User.email == normalize_email(email))
    return session.execute(statement).scalar_one_or_none()


def register_user(session: Session, email: str, display_name: str, password: str) -> User:
    """Register a standard local user with a secure password hash."""
    normalized_email = normalize_email(email)
    if get_user_by_email(session, normalized_email) is not None:
        raise DuplicateUserError("User already exists")

    user = User(
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        role=STANDARD_ROLE,
        is_active=True,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise DuplicateUserError("User already exists") from exc
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> User | AuthFailure:
    """Authenticate an active local user with a generic failure result."""
    user = get_user_by_email(session, email)
    if user is None or not user.is_active:
        return AuthFailure()
    if not verify_password(password, user.password_hash):
        return AuthFailure()
    return user


def bootstrap_admin(
    session: Session,
    email: str,
    display_name: str,
    password: str,
    *,
    update_password: bool = True,
) -> User:
    """Create or update an admin user idempotently for operator bootstrap."""
    normalized_email = normalize_email(email)
    cleaned_name = display_name.strip()
    if not normalized_email or not cleaned_name or not password:
        raise InvalidBootstrapInputError("Email, display name, and password are required")
    try:
        _email_adapter.validate_python(normalized_email)
    except ValidationError as exc:
        raise InvalidBootstrapInputError("A valid email address is required") from exc
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise InvalidBootstrapInputError("Password must be at least 8 characters")

    user = get_user_by_email(session, normalized_email)
    if user is None:
        user = User(
            email=normalized_email,
            display_name=cleaned_name,
            password_hash=hash_password(password),
            role=ADMIN_ROLE,
            is_active=True,
        )
        session.add(user)
    else:
        user.display_name = cleaned_name
        user.role = ADMIN_ROLE
        user.is_active = True
        if update_password:
            user.password_hash = hash_password(password)

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise InvalidBootstrapInputError("Admin bootstrap could not be completed") from exc
    session.refresh(user)
    return user
