"""Tests for bootstrap_admin CLI module."""

from unittest.mock import MagicMock, patch

import pytest

from ai_qa.auth.bootstrap_admin import main


class TestBootstrapAdminMain:
    """Test bootstrap_admin main() CLI entrypoint."""

    def test_main_success(self) -> None:
        """Main correctly parses args and provisions the admin."""
        mock_user = MagicMock()
        mock_user.email = "admin@example.com"
        mock_user.display_name = "Admin"

        with (
            patch("ai_qa.auth.bootstrap_admin.create_session_factory") as mock_factory,
            patch("ai_qa.auth.bootstrap_admin.bootstrap_admin") as mock_bootstrap,
        ):
            mock_bootstrap.return_value = mock_user
            mock_session = MagicMock()
            mock_factory.return_value.return_value.__enter__.return_value = mock_session

            result = main(["--email", "admin@example.com", "--name", "Admin"])

        assert result == 0
        mock_bootstrap.assert_called_once_with(
            mock_session,
            "admin@example.com",
            "Admin",
        )

    def test_main_raises_system_exit_on_invalid_input(self) -> None:
        """InvalidBootstrapInputError becomes SystemExit."""
        from ai_qa.auth.service import InvalidBootstrapInputError

        with (
            patch("ai_qa.auth.bootstrap_admin.create_session_factory") as mock_factory,
            patch("ai_qa.auth.bootstrap_admin.bootstrap_admin") as mock_bootstrap,
        ):
            mock_bootstrap.side_effect = InvalidBootstrapInputError("Invalid input")
            mock_session = MagicMock()
            mock_factory.return_value.return_value.__enter__.return_value = mock_session

            with pytest.raises(SystemExit, match="Invalid input"):
                main(["--email", "admin@example.com", "--name", "Admin"])

    def test_main_raises_system_exit_on_db_error(self) -> None:
        """SQLAlchemyError becomes SystemExit."""
        from sqlalchemy.exc import SQLAlchemyError

        with (
            patch("ai_qa.auth.bootstrap_admin.create_session_factory") as mock_factory,
            patch("ai_qa.auth.bootstrap_admin.bootstrap_admin") as mock_bootstrap,
        ):
            mock_bootstrap.side_effect = SQLAlchemyError("DB error")
            mock_session = MagicMock()
            mock_factory.return_value.return_value.__enter__.return_value = mock_session

            with pytest.raises(SystemExit, match="database error"):
                main(["--email", "admin@example.com", "--name", "Admin"])
