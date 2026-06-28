"""Custom SQLAlchemy types."""

from typing import Any, cast

from cryptography.fernet import Fernet
from sqlalchemy.types import String, Text, TypeDecorator

from ai_qa.config import AppSettings

_fernet_instance: Fernet | None = None
_user_secrets_fernet_instance: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is None:
        settings = AppSettings()
        _fernet_instance = Fernet(settings.db_encryption_key.encode("utf-8"))
    return _fernet_instance


def get_user_secrets_fernet() -> Fernet:
    """Return a cached Fernet bound to ``settings.user_secrets_encryption_key``.

    Kept separate from :func:`get_fernet` so per-user secrets are encrypted with
    a dedicated key (AC1 / key separation) rather than the shared DB key.
    """
    global _user_secrets_fernet_instance
    if _user_secrets_fernet_instance is None:
        settings = AppSettings()
        _user_secrets_fernet_instance = Fernet(settings.user_secrets_encryption_key.encode("utf-8"))
    return _user_secrets_fernet_instance


class EncryptedString(TypeDecorator[str]):
    """
    SQLAlchemy TypeDecorator that encrypts a string before saving to the DB
    and decrypts it when retrieving.
    Uses Fernet symmetric encryption.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        # Encrypt and return as string (database stores it as string/varchar)
        return get_fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        try:
            # Decrypt back to original string
            return get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            # If decryption fails (e.g., key changed or data is corrupt),
            # return the raw value or handle the error appropriately.
            # In a production environment, you might log this.
            return cast(str, value)


class UserSecretEncryptedString(TypeDecorator[str]):
    """Encrypts per-user secrets with the dedicated user-secrets Fernet key.

    Mirrors :class:`EncryptedString` semantics (None passthrough, encrypt-on-write,
    decrypt-on-read, corrupt-value fallback) but binds to
    :func:`get_user_secrets_fernet` so user secrets are isolated from the shared
    ``db_encryption_key`` (AC1).
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_user_secrets_fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        try:
            return get_user_secrets_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            # Corrupt or foreign-key ciphertext: treat as missing so callers
            # raise the UX-DR12 "key not configured" error instead of sending
            # garbage to the provider (Task 6 hardening — scope: this type only).
            return None


class UserSecretEncryptedText(TypeDecorator[str]):
    """``UserSecretEncryptedString`` for LARGE values (TEXT-backed, no length cap).

    Used for captured browser-session blobs (``storageState`` JSON, 2-10 KB+, larger
    after encryption) which would overflow the ``String(1024)`` per-user-secret column.
    Same dedicated user-secrets Fernet key and None/corrupt-value semantics.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return get_user_secrets_fernet().encrypt(str(value).encode("utf-8")).decode("utf-8")

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        try:
            return get_user_secrets_fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except Exception:
            return None
