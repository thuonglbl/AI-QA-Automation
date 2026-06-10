"""API tests for admin E2E test execution endpoints."""

import subprocess
import zipfile
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.auth.password import hash_password
from ai_qa.auth.service import ADMIN_ROLE, STANDARD_ROLE
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User


@pytest.fixture
def admin_client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(list[Table], [User.__table__, Project.__table__, ProjectMembership.__table__]),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db_session() -> Generator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    engine.dispose()


def _session_from_override(client: TestClient) -> Generator[Session]:
    app = cast(FastAPI, client.app)
    db_override = app.dependency_overrides[get_db_session_dependency]
    return cast(Generator[Session], db_override())


def _create_user(client: TestClient, email: str, role: str, *, active: bool = True) -> User:
    session_gen = _session_from_override(client)
    session = next(session_gen)
    try:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=hash_password("super-secret"),
            role=role,
            is_active=active,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session_gen.close()


def _token(client: TestClient, user: User) -> str:
    app = cast(FastAPI, client.app)
    session_manager = SessionManager(app.state.settings)
    session = session_manager.create_session(
        {
            "user_id": str(user.id),
            "email": user.email,
            "name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
        }
    )
    return session_manager.encode_session(session)  # type: ignore[no-any-return]


def _auth_headers(client: TestClient, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, user)}"}


class TestRunE2ETestsEndpoint:
    """Tests for POST /api/admin/tests/e2e."""

    def test_standard_user_cannot_trigger_e2e_tests(self, admin_client: TestClient) -> None:
        """Non-admin users must be rejected with 403."""
        standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

        response = admin_client.post(
            "/api/admin/tests/e2e",
            headers=_auth_headers(admin_client, standard),
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    def test_unauthenticated_cannot_trigger_e2e_tests(self, admin_client: TestClient) -> None:
        """Unauthenticated requests must be rejected with 401."""
        response = admin_client.post("/api/admin/tests/e2e")

        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"

    def test_admin_triggers_e2e_tests_with_passed_result(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """Admin can trigger tests and receives structured JSON result when tests pass."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        # Create a fake playwright-report/index.html so report_available is True
        report_dir = tmp_path / "playwright-report"
        report_dir.mkdir()
        (report_dir / "index.html").write_text("<html>Report</html>")

        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = b"5 passed"
        mock_result.stderr = b""

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value="npx"),
            patch("ai_qa.api.admin.subprocess.run", return_value=mock_result) as mock_run,
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["exit_code"] == 0, data
        assert data["passed"] is True
        assert data["report_available"] is True
        assert "5 passed" in data["stdout"]
        assert data["stderr"] == ""

        # Verify subprocess was called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "--headed" in call_args.args[0]
        assert call_args.kwargs.get("timeout") == 900

    def test_admin_triggers_e2e_tests_with_failed_result(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """When tests fail, endpoint returns passed=False with non-zero exit code."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stdout = b"2 passed, 1 failed"
        mock_result.stderr = b"Error: assertion failed"

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value="npx"),
            patch("ai_qa.api.admin.subprocess.run", return_value=mock_result),
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 200
        data = response.json()
        assert data["exit_code"] == 1
        assert data["passed"] is False
        assert data["report_available"] is False  # no report dir created

    def test_e2e_endpoint_returns_500_when_npx_not_found(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """Returns 500 when npx is not available in PATH."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value=None),
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 200
        assert "npx not found" in response.json()["stderr"]

    def test_e2e_endpoint_returns_504_on_timeout(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """Returns 504 when subprocess times out."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value="npx"),
            patch(
                "ai_qa.api.admin.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="npx", timeout=900),
            ),
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 200
        assert "timed out" in response.json()["stderr"]

    def test_e2e_endpoint_returns_500_when_frontend_dir_missing(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """Returns 500 when the frontend directory does not exist."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
        non_existent_path = tmp_path / "does_not_exist"

        with patch("ai_qa.api.admin._FRONTEND_DIR", non_existent_path):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 200
        assert "Frontend directory not found" in response.json()["stderr"]

    def test_slow_motion_env_var_is_set(self, admin_client: TestClient, tmp_path: Path) -> None:
        """Verify PLAYWRIGHT_SLOW_MO env var is passed to the subprocess."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = b""
        mock_result.stderr = b""

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value="npx"),
            patch("ai_qa.api.admin.subprocess.run", return_value=mock_result) as mock_run,
        ):
            admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        call_kwargs = mock_run.call_args.kwargs
        assert "PLAYWRIGHT_SLOW_MO" in call_kwargs["env"]
        assert call_kwargs["env"]["PLAYWRIGHT_SLOW_MO"] == "500"


class TestDownloadE2EReportEndpoint:
    """Tests for GET /api/admin/tests/e2e/report."""

    def test_standard_user_cannot_download_report(self, admin_client: TestClient) -> None:
        """Non-admin users must be rejected with 403."""
        standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

        response = admin_client.get(
            "/api/admin/tests/e2e/report",
            headers=_auth_headers(admin_client, standard),
        )

        assert response.status_code == 403

    def test_unauthenticated_cannot_download_report(self, admin_client: TestClient) -> None:
        """Unauthenticated requests must be rejected with 401."""
        response = admin_client.get("/api/admin/tests/e2e/report")

        assert response.status_code == 401

    def test_download_returns_404_when_no_report_exists(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """Returns 404 when no playwright-report directory or index.html exists."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        with patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path):
            response = admin_client.get(
                "/api/admin/tests/e2e/report",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 404
        assert "No E2E report available" in response.json()["detail"]

    def test_admin_can_download_report_as_zip(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """Admin receives a valid zip archive containing the report files."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        # Set up a fake playwright-report directory
        report_dir = tmp_path / "playwright-report"
        report_dir.mkdir()
        (report_dir / "index.html").write_text("<html>Report</html>")
        (report_dir / "data.json").write_text('{"tests": []}')

        with patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path):
            response = admin_client.get(
                "/api/admin/tests/e2e/report",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

        # Validate the zip contents
        zip_content = BytesIO(response.content)
        with zipfile.ZipFile(zip_content) as zf:
            names = zf.namelist()
            assert "index.html" in names
            assert "data.json" in names
