"""Tests for UserSecretEncryptedString — key separation from db_encryption_key."""

from unittest.mock import MagicMock

import pytest
from cryptography.fernet import InvalidToken

from ai_qa.db.types import (
    UserSecretEncryptedString,
    get_fernet,
    get_user_secrets_fernet,
)


class TestGetUserSecretsFernet:
    def test_returns_fernet_instance(self) -> None:
        import ai_qa.db.types as types_module

        original = types_module._user_secrets_fernet_instance
        types_module._user_secrets_fernet_instance = None
        try:
            fernet = get_user_secrets_fernet()
            assert fernet is not None
        finally:
            types_module._user_secrets_fernet_instance = original

    def test_singleton_behavior(self) -> None:
        assert get_user_secrets_fernet() is get_user_secrets_fernet()


class TestUserSecretEncryptedString:
    @pytest.fixture
    def enc_type(self) -> UserSecretEncryptedString:
        return UserSecretEncryptedString()

    @pytest.fixture
    def dialect(self) -> MagicMock:
        return MagicMock()

    def test_process_bind_param_none(
        self, enc_type: UserSecretEncryptedString, dialect: MagicMock
    ) -> None:
        assert enc_type.process_bind_param(None, dialect) is None

    def test_process_result_value_none(
        self, enc_type: UserSecretEncryptedString, dialect: MagicMock
    ) -> None:
        assert enc_type.process_result_value(None, dialect) is None

    def test_bind_output_differs_from_plaintext(
        self, enc_type: UserSecretEncryptedString, dialect: MagicMock
    ) -> None:
        result = enc_type.process_bind_param("super-secret-key", dialect)
        assert result is not None
        assert isinstance(result, str)
        assert result != "super-secret-key"

    def test_encrypt_decrypt_roundtrip(
        self, enc_type: UserSecretEncryptedString, dialect: MagicMock
    ) -> None:
        encrypted = enc_type.process_bind_param("super-secret-key", dialect)
        decrypted = enc_type.process_result_value(encrypted, dialect)
        assert decrypted == "super-secret-key"

    def test_corrupt_value_returns_none(
        self, enc_type: UserSecretEncryptedString, dialect: MagicMock
    ) -> None:
        # Hardening (db/types.py): undecryptable ciphertext is treated as missing
        # (returns None) so callers raise "key not configured" instead of sending
        # garbage to a provider — never echo the raw stored value back.
        assert enc_type.process_result_value("not-encrypted", dialect) is None

    def test_cache_ok(self) -> None:
        assert UserSecretEncryptedString.cache_ok is True

    def test_not_decryptable_with_db_encryption_key(
        self, enc_type: UserSecretEncryptedString, dialect: MagicMock
    ) -> None:
        """Key separation: ciphertext from the user-secrets key must NOT decrypt
        with the shared db_encryption_key Fernet (AC1)."""
        encrypted = enc_type.process_bind_param("super-secret-key", dialect)
        assert encrypted is not None
        with pytest.raises(InvalidToken):
            get_fernet().decrypt(encrypted.encode("utf-8"))
