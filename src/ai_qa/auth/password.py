"""Local password hashing helpers."""

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using the configured secure password hasher."""
    return str(_password_hash.hash(plain_password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored one-way hash."""
    try:
        return bool(_password_hash.verify(plain_password, hashed_password))
    except Exception:
        return False
