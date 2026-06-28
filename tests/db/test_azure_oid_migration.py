"""Round-trip test for the azure_oid + nullable-password_hash migration (23.3).

Runs the migration's ``upgrade()`` / ``downgrade()`` against an in-memory SQLite
``users`` table shaped like the pre-migration schema, asserting the column +
unique index appear and password_hash relaxes to nullable, then reverts.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"

_PRE_MIGRATION_USERS = (
    "CREATE TABLE users ("
    "id TEXT PRIMARY KEY, "
    "email TEXT NOT NULL UNIQUE, "
    "display_name TEXT NOT NULL, "
    "password_hash VARCHAR(255) NOT NULL, "
    "role VARCHAR(50) NOT NULL DEFAULT 'standard', "
    "is_active BOOLEAN NOT NULL DEFAULT 1, "
    "timezone VARCHAR(64) NOT NULL DEFAULT 'UTC', "
    "created_at DATETIME, updated_at DATETIME)"
)


def _load_migration(glob_pattern: str) -> ModuleType:
    path = next(_VERSIONS.glob(glob_pattern))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_azure_oid_migration_round_trips_on_sqlite() -> None:
    mig = _load_migration("e1a2c3d4f5b6_*.py")
    engine = sa.create_engine("sqlite://")
    try:
        with engine.connect() as conn:
            conn.execute(sa.text(_PRE_MIGRATION_USERS))
            ctx = MigrationContext.configure(conn)

            with Operations.context(ctx):
                mig.upgrade()
            cols = {c["name"]: c for c in sa.inspect(conn).get_columns("users")}
            assert "azure_oid" in cols
            assert cols["password_hash"]["nullable"] is True
            index_names = {i["name"] for i in sa.inspect(conn).get_indexes("users")}
            assert "ix_users_azure_oid" in index_names

            with Operations.context(ctx):
                mig.downgrade()
            cols_after = {c["name"]: c for c in sa.inspect(conn).get_columns("users")}
            assert "azure_oid" not in cols_after
            assert cols_after["password_hash"]["nullable"] is False
    finally:
        engine.dispose()


def test_migration_chains_off_current_head() -> None:
    mig = _load_migration("e1a2c3d4f5b6_*.py")
    assert mig.down_revision == "d5e8c1b9f3a2"
