"""Tests for the controlled Playwright execution runner (Stories 14.2/14.4).

Hermetic: no real browser is launched — ``subprocess.run`` and ``probe_browser_availability``
are patched. The parser/scrubber/command-builder/grouping are tested directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from ai_qa.pipelines import script_runner as sr
from ai_qa.pipelines.script_runner import (
    BrowserSpec,
    ScriptToRun,
    browser_spec_from_label,
    build_pytest_command,
    build_subprocess_env,
    classify_failure,
    group_invocations,
    parse_junit_xml,
    run_scripts,
    scrub_secrets,
)

_SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4" failures="1" errors="1" skipped="1">
    <testcase classname="test_0_test_a" name="test_login[chromium]" time="0.12"/>
    <testcase classname="test_1_test_b" name="test_search[chromium]" time="0.30">
      <failure message="AssertionError: not visible" type="AssertionError">expect(...).to_be_visible</failure>
    </testcase>
    <testcase classname="test_2_test_c" name="test_nav[chromium]" time="0.05">
      <error message="net::ERR_CONNECTION_REFUSED at page.goto" type="Error">navigation failed</error>
    </testcase>
    <testcase classname="test_3_test_d" name="test_skip[chromium]" time="0.0">
      <skipped message="skip"/>
    </testcase>
  </testsuite>
</testsuites>
"""


def _junit_path(cmd: list[str]) -> str:
    return next(a.split("=", 1)[1] for a in cmd if a.startswith("--junit-xml="))


def _engines(cmd: list[str]) -> list[str]:
    return [cmd[i + 1] for i, a in enumerate(cmd) if a == "--browser"]


class TestScrubSecrets:
    def test_redacts_bearer_and_keys(self) -> None:
        text = "Authorization: Bearer sk-ant-abc123XYZ\napi_key=supersecretvalue"
        out = scrub_secrets(text)
        assert out is not None
        assert "sk-ant-abc123XYZ" not in out
        assert "supersecretvalue" not in out
        assert "[REDACTED]" in out

    def test_none_passes_through(self) -> None:
        assert scrub_secrets(None) is None

    def test_caps_length(self) -> None:
        out = scrub_secrets("x" * 10000)
        assert out is not None
        assert len(out) <= 4100


class TestClassifyFailure:
    def test_assertion(self) -> None:
        assert classify_failure("AssertionError: nope", None) == "assertion"

    def test_timeout(self) -> None:
        assert classify_failure("TimeoutError: waiting", None) == "timeout"

    def test_selector(self) -> None:
        assert classify_failure("locator resolved to no element", None) == "selector"

    def test_navigation(self) -> None:
        assert classify_failure("net::ERR_CONNECTION_REFUSED", None) == "navigation"

    def test_default_error(self) -> None:
        assert classify_failure("something odd", None) == "error"


class TestBrowserMatrixHelpers:
    def test_browser_spec_from_label(self) -> None:
        assert browser_spec_from_label("chromium") == BrowserSpec("chromium")
        assert browser_spec_from_label("firefox") == BrowserSpec("firefox")
        assert browser_spec_from_label("edge") == BrowserSpec("chromium", "msedge")
        assert browser_spec_from_label("chrome") == BrowserSpec("chromium", "chrome")
        assert browser_spec_from_label("unknown") == BrowserSpec("chromium")

    def test_browser_spec_label(self) -> None:
        assert BrowserSpec("chromium").label == "chromium"
        assert BrowserSpec("chromium", "msedge").label == "msedge"

    def test_group_invocations_engines_share_one_call_channels_separate(self) -> None:
        specs = [
            BrowserSpec("chromium"),
            BrowserSpec("firefox"),
            BrowserSpec("chromium", "msedge"),
            BrowserSpec("chromium", "chrome"),
        ]
        invs = group_invocations(specs)
        assert len(invs) == 3  # one no-channel group + msedge + chrome
        assert invs[0].channel is None
        assert set(invs[0].engines) == {"chromium", "firefox"}
        channels = {inv.channel for inv in invs[1:]}
        assert channels == {"msedge", "chrome"}
        assert all(inv.label_override == inv.channel for inv in invs[1:])

    def test_group_invocations_only_channels(self) -> None:
        invs = group_invocations([BrowserSpec("chromium", "msedge")])
        assert len(invs) == 1
        assert invs[0].channel == "msedge"
        assert invs[0].label_override == "msedge"


class TestBuildPytestCommand:
    def test_isolation_flags_present(self) -> None:
        cmd = build_pytest_command(
            tmpdir="/tmp/x",
            results_xml="/tmp/x/results.xml",
            engines=["chromium"],
            headed=False,
            run_policy="continue",
        )
        assert "-o" in cmd and "addopts=" in cmd
        assert "--rootdir" in cmd
        assert "--junit-xml=/tmp/x/results.xml" in cmd
        assert _engines(cmd) == ["chromium"]
        assert "no:cov" in cmd
        assert "-x" not in cmd
        assert "--headed" not in cmd
        assert "--browser-channel" not in cmd

    def test_multiple_engines_and_channel(self) -> None:
        cmd = build_pytest_command(
            tmpdir="/tmp/x",
            results_xml="/tmp/x/r.xml",
            engines=["chromium", "firefox"],
            channel="msedge",
            headed=True,
            run_policy="stop_on_first_failure",
        )
        assert _engines(cmd) == ["chromium", "firefox"]
        assert "--browser-channel" in cmd
        assert "msedge" in cmd
        assert "-x" in cmd
        assert "--headed" in cmd


class TestBuildSubprocessEnv:
    def test_strips_secrets_and_sets_base_url(self) -> None:
        base = {
            "PATH": "/usr/bin",
            "ANTHROPIC_API_KEY": "sk-ant-xxx",
            "DATABASE_PASSWORD": "pw",
            "USER_SECRETS_ENCRYPTION_KEY": "k",
            "SOME_TOKEN": "t",
            "HOME": "/home/x",
        }
        env = build_subprocess_env(
            base_env=base, base_url="https://app.example.com", server_mode=False
        )
        assert env["APP_BASE_URL"] == "https://app.example.com"
        assert env["PATH"] == "/usr/bin"
        assert "ANTHROPIC_API_KEY" not in env
        assert "DATABASE_PASSWORD" not in env
        assert "USER_SECRETS_ENCRYPTION_KEY" not in env
        assert "SOME_TOKEN" not in env

    def test_server_mode_sets_deploy_flags(self) -> None:
        env = build_subprocess_env(base_env={"PATH": "/x"}, base_url="u", server_mode=True)
        assert env["E2E_NO_SANDBOX"] == "1"
        assert env["PLAYWRIGHT_IGNORE_HTTPS_ERRORS"] == "1"

    def test_app_base_url_trailing_slash_stripped(self) -> None:
        # A configured env URL with a trailing slash must not yield "host//path"
        # when scripts build URLs as f"{BASE_URL}/path".
        env = build_subprocess_env(
            base_env={"PATH": "/x"},
            base_url="https://int-app.corpnet.local/",
            server_mode=False,
        )
        assert env["APP_BASE_URL"] == "https://int-app.corpnet.local"


class TestParseJunitXml:
    def test_parses_all_statuses_and_provenance(self) -> None:
        id_a, id_b, id_c, id_d = uuid4(), uuid4(), uuid4(), uuid4()
        stem_map: dict[str, UUID | None] = {
            "test_0_test_a": id_a,
            "test_1_test_b": id_b,
            "test_2_test_c": id_c,
            "test_3_test_d": id_d,
        }
        results = parse_junit_xml(
            _SAMPLE_XML, default_browser="chromium", stem_to_artifact=stem_map
        )
        assert len(results) == 4
        by_name = {r.test_name: r for r in results}
        assert by_name["test_login"].status == "passed"
        assert by_name["test_login"].browser == "chromium"
        assert by_name["test_login"].source_artifact_id == id_a
        assert by_name["test_search"].status == "failed"
        assert by_name["test_search"].failure_classification == "assertion"
        assert by_name["test_nav"].status == "error"
        assert by_name["test_nav"].failure_classification == "navigation"
        assert by_name["test_skip"].status == "skipped"

    def test_scrubs_error_text(self) -> None:
        xml = (
            '<testsuites><testsuite><testcase classname="test_0_x" name="test_x[chromium]" '
            'time="0.1"><failure message="Authorization: Bearer sk-ant-leak">'
            "trace api_key=leakvalue</failure></testcase></testsuite></testsuites>"
        )
        results = parse_junit_xml(xml, default_browser="chromium", stem_to_artifact={})
        assert results[0].error_message is not None
        assert "sk-ant-leak" not in results[0].error_message
        assert results[0].stack_trace is not None
        assert "leakvalue" not in results[0].stack_trace


class TestRunScripts:
    def _patch_probe(self, available: list[BrowserSpec], unavailable=None):
        return patch.object(
            sr, "probe_browser_availability", return_value=(available, unavailable or [])
        )

    def test_run_scripts_parses_canned_xml(self, tmp_path: Path) -> None:
        id_a, id_b = uuid4(), uuid4()
        scripts = [
            ScriptToRun(
                name="test_a.py", content="def test_login(page): pass", source_artifact_id=id_a
            ),
            ScriptToRun(
                name="test_b.py", content="def test_search(page): pass", source_artifact_id=id_b
            ),
        ]

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            Path(_junit_path(cmd)).write_text(_SAMPLE_XML, encoding="utf-8")
            proc = MagicMock()
            proc.stdout, proc.stderr, proc.returncode = b"collected", b"", 1
            return proc

        with (
            self._patch_probe([BrowserSpec("chromium")]),
            patch.object(sr.subprocess, "run", side_effect=fake_run),
        ):
            result = run_scripts(
                scripts=scripts,
                base_url="https://app.example.com/path?token=secret",
                workdir=str(tmp_path),
                base_env={"PATH": "/usr/bin"},
            )

        assert result.summary.total == 4
        assert result.summary.passed == 1
        assert result.summary.failed == 1
        assert result.summary.errors == 1
        assert result.summary.skipped == 1
        assert result.summary.browsers == ["chromium"]
        assert "secret" not in result.summary.base_url_host
        assert result.summary.base_url_host == "app.example.com"
        assert any(f.name == "run.log" for f in result.produced_files)

    def test_run_scripts_multi_browser_merges_and_labels_channel(self, tmp_path: Path) -> None:
        scripts = [ScriptToRun(name="test_a.py", content="x", source_artifact_id=uuid4())]
        specs = [BrowserSpec("chromium"), BrowserSpec("firefox"), BrowserSpec("chromium", "msedge")]

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            cases = "".join(
                f'<testcase classname="test_0_test_a" name="test_login[{e}]" time="0.1"/>'
                for e in _engines(cmd)
            )
            Path(_junit_path(cmd)).write_text(
                f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8"
            )
            proc = MagicMock()
            proc.stdout, proc.stderr, proc.returncode = b"", b"", 0
            return proc

        with self._patch_probe(specs), patch.object(sr.subprocess, "run", side_effect=fake_run):
            result = run_scripts(
                scripts=scripts,
                base_url="https://app.example.com",
                browsers=specs,
                workdir=str(tmp_path),
                base_env={"PATH": "/usr/bin"},
            )

        # chromium + firefox (no-channel invocation) + msedge (channel-relabeled).
        browsers = {r.browser for r in result.results}
        assert browsers == {"chromium", "firefox", "msedge"}
        assert set(result.summary.browsers) == {"chromium", "firefox", "msedge"}

    def test_run_scripts_reports_unavailable_browser(self, tmp_path: Path) -> None:
        scripts = [ScriptToRun(name="test_a.py", content="x", source_artifact_id=uuid4())]

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            cases = "".join(
                f'<testcase classname="test_0_test_a" name="test_login[{e}]" time="0.1"/>'
                for e in _engines(cmd)
            )
            Path(_junit_path(cmd)).write_text(
                f"<testsuites><testsuite>{cases}</testsuite></testsuites>", encoding="utf-8"
            )
            proc = MagicMock()
            proc.stdout, proc.stderr, proc.returncode = b"", b"", 0
            return proc

        unavailable = [{"label": "webkit", "reason": "not installed"}]
        with (
            self._patch_probe([BrowserSpec("chromium")], unavailable),
            patch.object(sr.subprocess, "run", side_effect=fake_run),
        ):
            result = run_scripts(
                scripts=scripts,
                base_url="https://app.example.com",
                browsers=[BrowserSpec("chromium"), BrowserSpec("webkit")],
                workdir=str(tmp_path),
                base_env={"PATH": "/usr/bin"},
            )

        assert result.summary.unavailable_browsers == unavailable
        assert result.summary.browsers == ["chromium"]  # the available one still ran
        assert result.summary.total == 1

    def test_run_scripts_injects_storage_state_without_leaking(self, tmp_path: Path) -> None:
        scripts = [ScriptToRun(name="test_a.py", content="x", source_artifact_id=uuid4())]

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            Path(_junit_path(cmd)).write_text(
                '<testsuites><testsuite><testcase classname="test_0_test_a" '
                'name="test_login[chromium]" time="0.1"/></testsuite></testsuites>',
                encoding="utf-8",
            )
            proc = MagicMock()
            proc.stdout, proc.stderr, proc.returncode = b"", b"", 0
            return proc

        blob = {"cookies": [{"name": "sid", "value": "SECRETCOOKIE"}]}
        with (
            self._patch_probe([BrowserSpec("chromium")]),
            patch.object(sr.subprocess, "run", side_effect=fake_run),
        ):
            result = run_scripts(
                scripts=scripts,
                base_url="https://app.example.com",
                browsers=[BrowserSpec("chromium")],
                storage_state=blob,
                workdir=str(tmp_path),
                base_env={"PATH": "/usr/bin"},
            )

        # A conftest injecting storage_state was generated; the blob file exists.
        conftest = (tmp_path / "conftest.py").read_text(encoding="utf-8")
        assert "storage_state" in conftest
        assert (tmp_path / "storage_state.json").exists()
        # Leak canary: the cookie value never appears in any returned output.
        log = next(f for f in result.produced_files if f.name == "run.log").content.decode()
        assert "SECRETCOOKIE" not in log
        assert "SECRETCOOKIE" not in (result.stdout_tail or "")

    def test_run_scripts_collects_screenshots_and_traces(self, tmp_path: Path) -> None:
        scripts = [ScriptToRun(name="test_a.py", content="x", source_artifact_id=uuid4())]

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            Path(_junit_path(cmd)).write_text(_SAMPLE_XML, encoding="utf-8")
            out_arg = next(cmd[i + 1] for i, a in enumerate(cmd) if a == "--output")
            outdir = Path(out_arg) / "test_a_login"
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / "test-failed-1.png").write_bytes(b"PNGDATA")
            (outdir / "trace.zip").write_bytes(b"ZIPDATA")
            proc = MagicMock()
            proc.stdout, proc.stderr, proc.returncode = b"", b"", 1
            return proc

        with (
            self._patch_probe([BrowserSpec("chromium")]),
            patch.object(sr.subprocess, "run", side_effect=fake_run),
        ):
            result = run_scripts(
                scripts=scripts,
                base_url="https://app.example.com",
                workdir=str(tmp_path),
                base_env={"PATH": "/usr/bin"},
            )

        kinds = {f.kind for f in result.produced_files}
        assert "execution_screenshot" in kinds
        assert "trace" in kinds
        assert "log" in kinds

    def test_run_scripts_missing_xml_synthesizes_errors(self, tmp_path: Path) -> None:
        scripts = [ScriptToRun(name="test_a.py", content="x", source_artifact_id=uuid4())]

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003 — no XML written
            proc = MagicMock()
            proc.stdout, proc.stderr, proc.returncode = b"", b"boom", 2
            return proc

        with (
            self._patch_probe([BrowserSpec("chromium")]),
            patch.object(sr.subprocess, "run", side_effect=fake_run),
        ):
            result = run_scripts(
                scripts=scripts,
                base_url="https://app.example.com",
                workdir=str(tmp_path),
                base_env={"PATH": "/usr/bin"},
            )

        assert result.summary.total == 1
        assert result.summary.errors == 1
        assert result.results[0].status == "error"
