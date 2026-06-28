"""API tests for admin E2E test execution endpoints."""

import asyncio
import subprocess
import zipfile
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api import admin as admin_mod
from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
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
    """Tests for the async E2E run endpoints (POST /tests/e2e + GET /tests/e2e/status)."""

    @pytest.fixture(autouse=True)
    def _reset_e2e_state(self) -> Generator[None]:
        """The run state is a module-level singleton — reset it around each test."""
        admin_mod._e2e_state.status = "idle"
        admin_mod._e2e_state.exit_code = None
        admin_mod._e2e_state.passed = None
        admin_mod._e2e_state.report_available = False
        admin_mod._e2e_state.stdout = ""
        admin_mod._e2e_state.stderr = ""
        admin_mod._e2e_task = None
        yield

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

    def test_admin_post_starts_background_run(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """A valid POST returns 202 + status 'running' and schedules the background run."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value="npx"),
            patch("ai_qa.api.admin._run_e2e_background", new_callable=AsyncMock) as mock_bg,
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "running"
        assert data["exit_code"] is None
        assert data["passed"] is None
        mock_bg.assert_called_once()

    def test_post_is_noop_while_a_run_is_in_progress(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """A second POST during a run returns the running state without starting another."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
        admin_mod._e2e_state.status = "running"
        # A genuinely live task must exist for the run to be considered in progress.
        live_task = MagicMock()
        live_task.done.return_value = False
        admin_mod._e2e_task = live_task

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value="npx"),
            patch("ai_qa.api.admin._run_e2e_background", new_callable=AsyncMock) as mock_bg,
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        assert response.status_code == 202
        assert response.json()["status"] == "running"
        mock_bg.assert_not_called()

    def test_post_reports_missing_npx(self, admin_client: TestClient, tmp_path: Path) -> None:
        """When npx is missing the POST completes immediately with an error message."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.shutil.which", return_value=None),
        ):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        data = response.json()
        assert data["status"] == "completed"
        assert "npx not found" in data["stderr"]

    def test_post_reports_missing_frontend_dir(
        self, admin_client: TestClient, tmp_path: Path
    ) -> None:
        """When the frontend dir is absent the POST completes immediately with an error."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)
        non_existent_path = tmp_path / "does_not_exist"

        with patch("ai_qa.api.admin._FRONTEND_DIR", non_existent_path):
            response = admin_client.post(
                "/api/admin/tests/e2e",
                headers=_auth_headers(admin_client, admin),
            )

        data = response.json()
        assert data["status"] == "completed"
        assert "Frontend directory not found" in data["stderr"]

    def test_status_returns_current_state(self, admin_client: TestClient) -> None:
        """The status endpoint reports the (reset) idle state for an admin."""
        admin = _create_user(admin_client, "admin@example.com", ADMIN_ROLE)

        response = admin_client.get(
            "/api/admin/tests/e2e/status",
            headers=_auth_headers(admin_client, admin),
        )

        assert response.status_code == 200
        assert response.json()["status"] == "idle"

    def test_standard_user_cannot_read_status(self, admin_client: TestClient) -> None:
        """Non-admin users must be rejected with 403 from the status endpoint."""
        standard = _create_user(admin_client, "standard@example.com", STANDARD_ROLE)

        response = admin_client.get(
            "/api/admin/tests/e2e/status",
            headers=_auth_headers(admin_client, standard),
        )

        assert response.status_code == 403

    def test_unauthenticated_cannot_read_status(self, admin_client: TestClient) -> None:
        """Unauthenticated requests must be rejected with 401 from the status endpoint."""
        response = admin_client.get("/api/admin/tests/e2e/status")

        assert response.status_code == 401

    def test_build_command_local_mode_is_headed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Local mode: headed + slow motion, reuses running servers, never forces CI."""
        monkeypatch.delenv("E2E_SERVER_MODE", raising=False)
        monkeypatch.delenv("E2E_HEADED", raising=False)
        monkeypatch.delenv("CI", raising=False)

        cmd, env = admin_mod._build_e2e_command_and_env("npx")

        assert "--headed" in cmd
        assert env["PLAYWRIGHT_SLOW_MO"] == "500"
        # E2E_DISABLE_WEBSERVER stops Playwright booting its own backend/Vite; CI is
        # never injected (CI=1 used to disable reuseExistingServer → the local
        # "port 8000 already used" failure).
        assert env["E2E_DISABLE_WEBSERVER"] == "1"
        assert "CI" not in env

    def test_build_command_headless_when_e2e_headed_zero(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """E2E_HEADED=0 drops --headed and zeroes slow motion."""
        monkeypatch.delenv("E2E_SERVER_MODE", raising=False)
        monkeypatch.setenv("E2E_HEADED", "0")

        cmd, env = admin_mod._build_e2e_command_and_env("npx")

        assert "--headed" not in cmd
        assert env["PLAYWRIGHT_SLOW_MO"] == "0"

    def test_build_command_server_mode_container_flags(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server mode → headless, sandbox disabled, TLS errors ignored, no own servers."""
        monkeypatch.setenv("E2E_SERVER_MODE", "1")
        monkeypatch.delenv("E2E_NO_SANDBOX", raising=False)
        monkeypatch.delenv("PLAYWRIGHT_IGNORE_HTTPS_ERRORS", raising=False)

        cmd, env = admin_mod._build_e2e_command_and_env("npx")

        assert "--headed" not in cmd
        assert env["E2E_DISABLE_WEBSERVER"] == "1"
        assert env["E2E_NO_SANDBOX"] == "1"
        assert env["PLAYWRIGHT_IGNORE_HTTPS_ERRORS"] == "1"
        assert env["PLAYWRIGHT_SLOW_MO"] == "0"

    def test_build_command_forwards_base_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A BASE_URL in the backend env reaches the Playwright subprocess env."""
        monkeypatch.setenv("BASE_URL", "https://ai-qa.ai-uat.corpdev.local")

        _, env = admin_mod._build_e2e_command_and_env("npx")

        assert env["BASE_URL"] == "https://ai-qa.ai-uat.corpdev.local"

    def test_background_run_records_pass(self, tmp_path: Path) -> None:
        """A zero exit code records passed=True and detects the HTML report."""
        report_dir = tmp_path / "playwright-report"
        report_dir.mkdir()
        (report_dir / "index.html").write_text("<html>Report</html>")

        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = b"5 passed"
        mock_result.stderr = b""

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.subprocess.run", return_value=mock_result),
        ):
            asyncio.run(admin_mod._run_e2e_background(["npx"], {"X": "1"}))

        assert admin_mod._e2e_state.status == "completed"
        assert admin_mod._e2e_state.passed is True
        assert admin_mod._e2e_state.exit_code == 0
        assert admin_mod._e2e_state.report_available is True
        assert "5 passed" in admin_mod._e2e_state.stdout

    def test_background_run_records_failure(self, tmp_path: Path) -> None:
        """A non-zero exit code records passed=False; with no report dir it is unavailable."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stdout = b"2 passed, 1 failed"
        mock_result.stderr = b"AssertionError"

        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch("ai_qa.api.admin.subprocess.run", return_value=mock_result),
        ):
            asyncio.run(admin_mod._run_e2e_background(["npx"], {"X": "1"}))

        assert admin_mod._e2e_state.status == "completed"
        assert admin_mod._e2e_state.passed is False
        assert admin_mod._e2e_state.exit_code == 1
        assert admin_mod._e2e_state.report_available is False

    def test_background_run_records_timeout(self, tmp_path: Path) -> None:
        """A subprocess timeout records a completed run with a timeout message."""
        with (
            patch("ai_qa.api.admin._FRONTEND_DIR", tmp_path),
            patch(
                "ai_qa.api.admin.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="npx", timeout=900),
            ),
        ):
            asyncio.run(admin_mod._run_e2e_background(["npx"], {"X": "1"}))

        assert admin_mod._e2e_state.status == "completed"
        assert admin_mod._e2e_state.passed is False
        assert "timed out" in admin_mod._e2e_state.stderr


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
