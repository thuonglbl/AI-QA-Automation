"""Tests for database configuration settings."""

from urllib.parse import urlsplit

from ai_qa.config import AppSettings, mask_database_url


def test_database_url_uses_explicit_url() -> None:
    settings = AppSettings(database_url="postgresql+psycopg://db:5432/app?user=test-user")

    assert settings.sqlalchemy_database_url == "postgresql+psycopg://db:5432/app?user=test-user"


def test_database_url_is_derived_from_parts_with_escaping() -> None:
    settings = AppSettings(
        database_host="localhost",
        database_port=5544,
        database_name="ai qa",
        database_user="user@example.com",
        database_password="<test-db-password>",
    )

    database_url = settings.sqlalchemy_database_url
    parts = urlsplit(database_url)

    assert parts.scheme == "postgresql+psycopg"
    assert parts.netloc == "user%40example.com:%3Ctest-db-password%3E@localhost:5544"
    assert parts.path == "/ai qa"


def test_mask_database_url_hides_password() -> None:
    masked = mask_database_url("postgresql+psycopg://test-user@localhost:5432/app")

    assert masked == "postgresql+psycopg://***@localhost:5432/app"
    assert "<test-db-password>" not in masked


def test_mask_database_url_without_credentials_is_unchanged() -> None:
    url = "postgresql+psycopg://localhost:5432/app"

    assert mask_database_url(url) == url
