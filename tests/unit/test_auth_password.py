"""Tests for secure local password hashing."""

from ai_qa.auth.password import hash_password, verify_password


def test_hash_password_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("correct horse battery staple")

    assert hashed != "correct horse battery staple"
    assert "correct horse battery staple" not in hashed
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False
