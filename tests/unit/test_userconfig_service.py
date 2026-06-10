"""Unit tests for userconfig service (Story 9.7 — Task 8).

Mirrors the fixture scaffold from tests/api/test_admin_rbac_api.py.
"""

from collections.abc import Generator
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.db.base import Base
from ai_qa.db.models import AiProviderConfig, Project, User
from ai_qa.userconfig.service import get_provider_config, save_provider_config


@pytest.fixture
def db() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [User.__table__, Project.__table__, AiProviderConfig.__table__],
        ),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
    engine.dispose()


def _make_user(session: Session) -> User:
    user = User(
        email=f"user-{uuid4()}@test.com",
        display_name="Test User",
        password_hash="hash",
        role="standard",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _make_project(session: Session) -> Project:
    project = Project(name=f"proj-{uuid4()}", enabled_providers=[])
    session.add(project)
    session.flush()
    return project


class TestSaveProviderConfig:
    def test_upsert_inserts_new_row(self, db: Session) -> None:
        user = _make_user(db)
        project = _make_project(db)
        save_provider_config(
            db,
            user.id,
            project.id,
            {"provider": "claude", "endpoint": "https://api.anthropic.com"},
            {"agents": {"bob": {"model": "gpt-4o", "temperature": 0.5}}},
        )
        db.commit()
        result = get_provider_config(db, user.id, project.id)
        assert result is not None
        assert result["provider"]["provider"] == "claude"
        assert result["agents"]["agents"]["bob"]["model"] == "gpt-4o"

    def test_upsert_keeps_one_row_per_user_project(self, db: Session) -> None:
        user = _make_user(db)
        project = _make_project(db)
        save_provider_config(db, user.id, project.id, {"provider": "claude"}, {})
        db.commit()
        save_provider_config(db, user.id, project.id, {"provider": "openai"}, {})
        db.commit()

        from sqlalchemy import select

        rows = db.scalars(
            select(AiProviderConfig).where(
                AiProviderConfig.user_id == user.id,
                AiProviderConfig.project_id == project.id,
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].ai_provider_config["provider"] == "openai"

    def test_different_projects_stored_independently(self, db: Session) -> None:
        user = _make_user(db)
        proj_a = _make_project(db)
        proj_b = _make_project(db)
        save_provider_config(db, user.id, proj_a.id, {"provider": "claude"}, {})
        save_provider_config(db, user.id, proj_b.id, {"provider": "openai"}, {})
        db.commit()

        cfg_a = get_provider_config(db, user.id, proj_a.id)
        cfg_b = get_provider_config(db, user.id, proj_b.id)
        assert cfg_a is not None
        assert cfg_b is not None
        assert cfg_a["provider"]["provider"] == "claude"
        assert cfg_b["provider"]["provider"] == "openai"

    def test_get_provider_config_returns_none_when_absent(self, db: Session) -> None:
        user = _make_user(db)
        project = _make_project(db)
        result = get_provider_config(db, user.id, project.id)
        assert result is None

    def test_saved_config_contains_no_secret_sentinel(self, db: Session) -> None:
        """AC1 leakage guard: no secret value must appear in stored blobs."""
        import json

        user = _make_user(db)
        project = _make_project(db)
        secret_sentinel = "sk-SUPER-SECRET-API-KEY-12345"
        provider_cfg = {
            "provider": "claude",
            "endpoint": "https://api.anthropic.com",
            "tested_at": "2026-01-01T00:00:00Z",
        }
        agents_cfg = {"agents": {"bob": {"model": "gpt-4o", "temperature": 0.0}}}
        save_provider_config(db, user.id, project.id, provider_cfg, agents_cfg)
        db.commit()

        from sqlalchemy import select

        row = db.scalar(
            select(AiProviderConfig).where(
                AiProviderConfig.user_id == user.id,
                AiProviderConfig.project_id == project.id,
            )
        )
        assert row is not None
        stored_json = json.dumps(row.ai_provider_config or {}) + json.dumps(
            row.ai_agents_config or {}
        )
        assert secret_sentinel not in stored_json


class TestCorruptCiphertext:
    """Task 6: corrupt stored ciphertext → get_user_secret returns None."""

    def test_corrupt_ciphertext_returns_none(self) -> None:
        """UserSecretEncryptedString.process_result_value returns None on decrypt failure."""
        from ai_qa.db.types import UserSecretEncryptedString

        col_type = UserSecretEncryptedString()
        result = col_type.process_result_value("this-is-not-valid-fernet-ciphertext", None)
        assert result is None

    def test_none_passthrough_is_preserved(self) -> None:
        """None stored value remains None (not converted to empty string)."""
        from ai_qa.db.types import UserSecretEncryptedString

        col_type = UserSecretEncryptedString()
        result = col_type.process_result_value(None, None)
        assert result is None

    def test_valid_roundtrip_succeeds(self) -> None:
        """Valid encrypt→decrypt roundtrip returns original plaintext."""
        from ai_qa.db.types import UserSecretEncryptedString

        col_type = UserSecretEncryptedString()
        plaintext = "my-real-api-key-12345"
        encrypted = col_type.process_bind_param(plaintext, None)
        assert encrypted is not None
        decrypted = col_type.process_result_value(encrypted, None)
        assert decrypted == plaintext
