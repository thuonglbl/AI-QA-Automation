"""ORM model for per-user encrypted secret storage.

``UserSecret`` separates the single secret-bearing column (``encrypted_value``)
from non-secret metadata (``secret_type``, ``status``, ``user_id``, timestamps)
to satisfy AC2. The encrypted column binds to the dedicated user-secrets Fernet
key via :class:`~ai_qa.db.types.UserSecretEncryptedString` (AC1).
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_qa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from ai_qa.db.types import UserSecretEncryptedString

if TYPE_CHECKING:
    from ai_qa.db.models import User


class UserSecret(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single encrypted secret owned by a user, keyed by secret type."""

    __tablename__ = "user_secrets"
    __table_args__ = (
        UniqueConstraint("user_id", "secret_type", name="uq_user_secrets_user_secret_type"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    secret_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="configured")
    encrypted_value: Mapped[str] = mapped_column(UserSecretEncryptedString(1024), nullable=False)

    user: Mapped["User"] = relationship(back_populates="secrets")
