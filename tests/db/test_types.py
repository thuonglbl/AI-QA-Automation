"""Tests for db/types.py - EncryptedString custom SQLAlchemy type."""

from unittest.mock import MagicMock

import pytest

from ai_qa.db.types import EncryptedString, get_fernet


class TestGetFernet:
    def test_returns_fernet_instance(self) -> None:
        import ai_qa.db.types as types_module

        # Reset singleton so we can test initialization
        original = types_module._fernet_instance
        types_module._fernet_instance = None
        try:
            fernet = get_fernet()
            assert fernet is not None
        finally:
            types_module._fernet_instance = original

    def test_singleton_behavior(self) -> None:
        """get_fernet() returns the same instance on repeated calls."""
        f1 = get_fernet()
        f2 = get_fernet()
        assert f1 is f2


class TestEncryptedString:
    @pytest.fixture
    def enc_type(self) -> EncryptedString:
        return EncryptedString()

    @pytest.fixture
    def dialect(self) -> MagicMock:
        return MagicMock()

    def test_process_bind_param_none(self, enc_type: EncryptedString, dialect: MagicMock) -> None:
        """None values pass through as None."""
        result = enc_type.process_bind_param(None, dialect)
        assert result is None

    def test_process_bind_param_encrypts_value(
        self, enc_type: EncryptedString, dialect: MagicMock
    ) -> None:
        """Non-None values are encrypted and returned as string."""
        result = enc_type.process_bind_param("my-secret", dialect)
        assert result is not None
        assert isinstance(result, str)
        assert result != "my-secret"

    def test_process_result_value_none(self, enc_type: EncryptedString, dialect: MagicMock) -> None:
        """None values pass through as None."""
        result = enc_type.process_result_value(None, dialect)
        assert result is None

    def test_process_result_value_decrypts(
        self, enc_type: EncryptedString, dialect: MagicMock
    ) -> None:
        """Encrypted values are properly decrypted."""
        # First encrypt, then decrypt
        encrypted = enc_type.process_bind_param("my-secret", dialect)
        decrypted = enc_type.process_result_value(encrypted, dialect)
        assert decrypted == "my-secret"

    def test_process_result_value_corrupt_returns_raw(
        self, enc_type: EncryptedString, dialect: MagicMock
    ) -> None:
        """If decryption fails, the raw value is returned."""
        result = enc_type.process_result_value("not-encrypted-data", dialect)
        assert result == "not-encrypted-data"

    def test_cache_ok(self) -> None:
        assert EncryptedString.cache_ok is True

    def test_encrypt_decrypt_roundtrip_various_types(
        self, enc_type: EncryptedString, dialect: MagicMock
    ) -> None:
        """Integers and other types that get str() called work correctly."""
        encrypted = enc_type.process_bind_param(12345, dialect)
        assert encrypted is not None
        decrypted = enc_type.process_result_value(encrypted, dialect)
        assert decrypted == "12345"
