"""Unit tests for Secrets service."""

from ai_qa.secrets.service import SecretsService


class TestSecretsService:
    def test_set_secret_encrypts_and_stores(self, db_session):
        service = SecretsService(db_session)
        secret = service.set_secret("test_key", "sensitive_value", "user-1")
        assert secret.key == "test_key"
        assert secret.value != "sensitive_value"  # Should be encrypted

    def test_get_secret_decrypts_value(self, db_session):
        service = SecretsService(db_session)
        service.set_secret("test_key", "sensitive_value", "user-1")
        value = service.get_secret("test_key", "user-1")
        assert value == "sensitive_value"

    def test_get_nonexistent_secret_returns_none(self, db_session):
        service = SecretsService(db_session)
        value = service.get_secret("nonexistent", "user-1")
        assert value is None

    def test_delete_secret_removes_entry(self, db_session):
        service = SecretsService(db_session)
        service.set_secret("test_key", "sensitive_value", "user-1")
        service.delete_secret("test_key", "user-1")
        value = service.get_secret("test_key", "user-1")
        assert value is None

    def test_list_secrets_returns_keys_only(self, db_session):
        service = SecretsService(db_session)
        service.set_secret("key1", "val1", "user-1")
        service.set_secret("key2", "val2", "user-1")
        secrets = service.list_secrets("user-1")
        keys = [s.key for s in secrets]
        assert "key1" in keys
        assert "key2" in keys

    def test_secret_isolation_by_user(self, db_session):
        service = SecretsService(db_session)
        service.set_secret("shared_key", "user1_val", "user-1")
        service.set_secret("shared_key", "user2_val", "user-2")
        val1 = service.get_secret("shared_key", "user-1")
        val2 = service.get_secret("shared_key", "user-2")
        assert val1 == "user1_val"
        assert val2 == "user2_val"
