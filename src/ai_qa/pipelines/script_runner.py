"""Controlled Playwright execution runner (Story 14.2).

Materialises approved pytest + pytest-playwright scripts to a temp dir and runs
them in an isolated ``pytest`` subprocess (isolated from the FastAPI event loop and
from the repo's coverage ``addopts``), capturing structured results via the built-in
``--junit-xml`` reporter.

This module is deliberately agent/DB-free: the agent (``JackAgent``) calls
``run_scripts`` inside ``asyncio.to_thread`` and persists the structured ``RunResult``.

Forward-compat seams (used by later stories, single-valued in 14.2):
- ``browser`` / ``storage_state_path`` params → Story 14.4 (multi-browser + auth).
- ``RunResult.produced_files`` → Story 14.3 (persist outputs through the artifact service).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

logger = logging.getLogger(__name__)

# Status strings (match TestExecutionResult.status).
STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"

# Failure classifications.
CLASS_ASSERTION = "assertion"
CLASS_TIMEOUT = "timeout"
CLASS_SELECTOR = "selector"
CLASS_NAVIGATION = "navigation"
CLASS_ERROR = "error"

_MAX_FIELD_LEN = 4000

# Secret-shaped patterns redacted from any captured error/trace text before it is
# returned (leak-canary convention). Order matters — broader header rules first.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(authorization|cookie|set-cookie|x-api-key|proxy-authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd|pwd)\s*[\"':=]+\s*\S+"),
]


@dataclass(frozen=True)
class ScriptToRun:
    """One approved script to execute."""

    name: str
    content: str
    source_artifact_id: UUID | None = None


@dataclass(frozen=True)
class BrowserSpec:
    """A browser target (Story 14.4).

    ``engine`` is a Playwright engine (``chromium``/``firefox``/``webkit``); ``channel``
    is a Chromium channel (``msedge``/``chrome``) or ``None``. ``label`` is the channel
    name when set, else the engine — this is the ``TestExecutionResult.browser`` value.
    """

    engine: str
    channel: str | None = None

    @property
    def label(self) -> str:
        return self.channel or self.engine


# Map a UI browser label → a BrowserSpec. Edge/Chrome are Chromium channels.
_LABEL_TO_SPEC: dict[str, BrowserSpec] = {
    "chromium": BrowserSpec("chromium"),
    "firefox": BrowserSpec("firefox"),
    "webkit": BrowserSpec("webkit"),
    "chrome": BrowserSpec("chromium", "chrome"),
    "msedge": BrowserSpec("chromium", "msedge"),
    "edge": BrowserSpec("chromium", "msedge"),
}


def browser_spec_from_label(label: str) -> BrowserSpec:
    """Resolve a UI browser label to a :class:`BrowserSpec` (defaults to chromium)."""
    return _LABEL_TO_SPEC.get(label.strip().lower(), BrowserSpec("chromium"))


@dataclass
class TestResult:
    """Structured result for a single executed test (one ``(test, browser)``)."""

    __test__ = False  # not a pytest test class (name starts with "Test")

    test_name: str
    browser: str
    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    failure_classification: str | None = None
    source_artifact_id: UUID | None = None
    # Application role this test ran AS (the captured-session role). Set by Jack after a
    # per-role run group (Slice 6); None for role-less / single-session runs.
    role: str | None = None


@dataclass
class ProducedFile:
    """A file the runner produced in its temp dir (persisted by Story 14.3)."""

    name: str
    content: bytes
    kind: str


@dataclass
class RunSummary:
    """Run-level summary (persisted to ``AgentRun.execution_metadata``)."""

    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: int
    browsers: list[str]
    base_url_host: str
    run_policy: str
    started_at: str
    completed_at: str
    unavailable_browsers: list[dict[str, str]] = field(default_factory=list)


@dataclass
class RunResult:
    """The full structured outcome of a Jack execution run."""

    results: list[TestResult]
    summary: RunSummary
    produced_files: list[ProducedFile] = field(default_factory=list)
    stdout_tail: str = ""
    stderr_tail: str = ""


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without launching browsers)
# ---------------------------------------------------------------------------


def scrub_secrets(text: str | None) -> str | None:
    """Redact secret-shaped substrings and cap length. ``None`` passes through."""
    if not text:
        return text
    scrubbed = text
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub("[REDACTED]", scrubbed)
    if len(scrubbed) > _MAX_FIELD_LEN:
        scrubbed = scrubbed[:_MAX_FIELD_LEN] + "… [truncated]"
    return scrubbed


def classify_failure(message: str | None, trace: str | None) -> str:
    """Best-effort failure classification from the message/trace text."""
    blob = f"{message or ''}\n{trace or ''}".lower()
    if "timeout" in blob or "timeouterror" in blob:
        return CLASS_TIMEOUT
    if (
        "no node found" in blob
        or "no element" in blob
        or "locator" in blob
        or "selector" in blob
        or "waiting for selector" in blob
    ):
        return CLASS_SELECTOR
    if (
        "err_connection" in blob
        or "net::err" in blob
        or "navigation" in blob
        or "err_name_not_resolved" in blob
        or "page.goto" in blob
    ):
        return CLASS_NAVIGATION
    if "assertionerror" in blob or "expect(" in blob or "to_be_visible" in blob:
        return CLASS_ASSERTION
    return CLASS_ERROR


def safe_filename(name: str) -> str:
    """Reduce an artifact name to a filesystem-safe stem (keeps it readable)."""
    stem = name[:-3] if name.endswith(".py") else name
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_")
    return stem or "script"


def build_pytest_command(
    *,
    tmpdir: str,
    results_xml: str,
    engines: list[str],
    channel: str | None = None,
    headed: bool,
    run_policy: str,
    output_dir: str | None = None,
    capture_screenshots: bool = False,
    capture_traces: bool = False,
    per_test_timeout: int | None = None,
) -> list[str]:
    """Build the isolated pytest command line (no repo addopts/coverage inheritance).

    ``engines`` are run via repeated ``--browser`` flags (pytest-playwright parametrizes
    each test per engine). ``channel`` adds a single ``--browser-channel`` (per-invocation,
    so a distinct channel needs its own call — see ``group_invocations``).
    """
    cmd = ["pytest", tmpdir]
    for engine in engines:
        cmd += ["--browser", engine]
    if channel:
        cmd += ["--browser-channel", channel]
    cmd += [
        f"--junit-xml={results_xml}",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:cov",
        "-o",
        "addopts=",
        "--rootdir",
        tmpdir,
    ]
    if output_dir is not None:
        cmd += ["--output", output_dir]
    if capture_screenshots:
        cmd += ["--screenshot", "only-on-failure"]
    if capture_traces:
        cmd += ["--tracing", "retain-on-failure"]
    if headed:
        cmd.append("--headed")
    if run_policy == "stop_on_first_failure":
        cmd.append("-x")
    if per_test_timeout and per_test_timeout > 0:
        # Per-script isolation (Story 14.2 Decision #6): kill a single hung test instead of
        # letting it consume the whole wall-clock budget. Thread method is cross-platform.
        cmd += ["--timeout", str(per_test_timeout), "--timeout-method=thread"]
    return cmd


@dataclass(frozen=True)
class _Invocation:
    """One pytest invocation group: engines sharing a channel (or no channel)."""

    engines: list[str]
    channel: str | None
    label_override: str | None  # channel groups tag every result with the channel label


def group_invocations(specs: list[BrowserSpec]) -> list[_Invocation]:
    """Group specs into pytest invocations: no-channel engines share one call; each
    distinct channel gets its own call (``--browser-channel`` is per-invocation)."""
    invocations: list[_Invocation] = []
    no_channel = [s.engine for s in specs if not s.channel]
    if no_channel:
        invocations.append(_Invocation(engines=no_channel, channel=None, label_override=None))
    for spec in specs:
        if spec.channel:
            invocations.append(
                _Invocation(engines=[spec.engine], channel=spec.channel, label_override=spec.label)
            )
    return invocations


def probe_browser_availability(
    specs: list[BrowserSpec],
) -> tuple[list[BrowserSpec], list[dict[str, str]]]:
    """Probe each spec by a cheap headless launch; return (available, unavailable).

    A missing browser/channel is reported with a clear reason — it never aborts the rest
    (AC2). Integration-only in practice; unit tests patch this function.
    """
    available: list[BrowserSpec] = []
    unavailable: list[dict[str, str]] = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - playwright is a hard dependency
        return [], [{"label": s.label, "reason": "Playwright is not installed"} for s in specs]
    with sync_playwright() as p:
        for spec in specs:
            try:
                btype = getattr(p, spec.engine)
                launch_kwargs: dict[str, Any] = {"headless": True}
                if spec.channel:
                    launch_kwargs["channel"] = spec.channel
                browser = btype.launch(**launch_kwargs)
                browser.close()
                available.append(spec)
            except Exception as exc:  # noqa: BLE001 — any launch failure → "unavailable"
                unavailable.append({"label": spec.label, "reason": _short_reason(exc)})
    return available, unavailable


def _short_reason(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:200]


def _write_storage_state_conftest(tmp_path: Path, storage_state_file: str) -> None:
    """Generate a conftest that injects the captured ``storageState`` into every context."""
    conftest = (
        "import pytest\n\n"
        "@pytest.fixture(scope='session')\n"
        "def browser_context_args(browser_context_args):\n"
        f"    return {{**browser_context_args, 'storage_state': {storage_state_file!r}}}\n"
    )
    (tmp_path / "conftest.py").write_text(conftest, encoding="utf-8")


# Allowlist of non-secret env keys (and key prefixes) the runner subprocess legitimately
# needs (OS / Python / Playwright infra). Everything else from the parent process is DROPPED
# so a secret-shaped var (DATABASE_URL, *_ACCESS_KEY, api keys, …) can NEVER leak into a
# process running approved-but-LLM-generated Playwright code (secret containment, conv. #1).
_ENV_ALLOW_EXACT = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "OS",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TZ",
        "TERM",
        "DISPLAY",
        "XAUTHORITY",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "VIRTUAL_ENV",
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
    }
)
_ENV_ALLOW_PREFIX = ("PLAYWRIGHT", "PYTEST", "CHROME", "NODE")


def _env_allowed(key: str) -> bool:
    upper = key.upper()
    return upper in _ENV_ALLOW_EXACT or upper.startswith(_ENV_ALLOW_PREFIX)


def build_subprocess_env(
    *,
    base_env: dict[str, str],
    base_url: str,
    server_mode: bool,
) -> dict[str, str]:
    """Build a minimal allowlisted subprocess env: OS/Python/Playwright infra + run flags only.

    The subprocess runs approved (LLM-generated) Playwright code, so the parent's secrets must
    NOT be inherited. An allowlist (rather than a name denylist) guarantees a new secret-shaped
    var — e.g. ``DATABASE_URL`` or ``SEAWEEDFS_ACCESS_KEY`` — can never leak (convention #1).
    """
    env = {k: v for k, v in base_env.items() if _env_allowed(k)}
    env["APP_BASE_URL"] = base_url
    env["FORCE_COLOR"] = "0"
    env["PLAYWRIGHT_HTML_REPORT_OPEN"] = "never"
    if server_mode:
        env.setdefault("E2E_NO_SANDBOX", "1")
        env.setdefault("PLAYWRIGHT_IGNORE_HTTPS_ERRORS", "1")
    return env


def _strip_url_userinfo(url: str) -> str:
    """Remove any embedded ``user:pass@`` from a URL, keeping scheme/host/port/path/query.

    The runner persists the host into the visible report and exports the URL as APP_BASE_URL;
    embedded basic-auth credentials must never reach those channels (auth is via the captured
    session, not the URL).
    """
    parts = urlsplit(url)
    if not parts.hostname:
        return url
    netloc = f"{parts.hostname}:{parts.port}" if parts.port else parts.hostname
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def parse_junit_xml(
    xml_text: str,
    *,
    default_browser: str,
    stem_to_artifact: dict[str, UUID | None],
) -> list[TestResult]:
    """Parse pytest JUnit XML into structured per-test results.

    ``stem_to_artifact`` maps a materialised module stem (``test_0_login``) to the
    source script artifact id so each result links back to its origin.
    """
    root = ET.fromstring(xml_text)
    results: list[TestResult] = []
    for case in root.iter("testcase"):
        raw_name = case.get("name", "")
        classname = case.get("classname", "")
        browser = _browser_from_name(raw_name) or default_browser
        test_name = _strip_browser_suffix(raw_name)
        duration_ms = _seconds_to_ms(case.get("time"))
        source_artifact_id = _resolve_artifact(classname, raw_name, stem_to_artifact)

        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")

        status = STATUS_PASSED
        message: str | None = None
        trace: str | None = None
        classification: str | None = None
        node = None
        if failure is not None:
            status = STATUS_FAILED
            node = failure
        elif error is not None:
            status = STATUS_ERROR
            node = error
        elif skipped is not None:
            status = STATUS_SKIPPED
            node = skipped

        if node is not None and status in (STATUS_FAILED, STATUS_ERROR):
            message = scrub_secrets(node.get("message") or None)
            trace = scrub_secrets((node.text or "").strip() or None)
            classification = classify_failure(message, trace)

        results.append(
            TestResult(
                test_name=test_name,
                browser=browser,
                status=status,
                duration_ms=duration_ms,
                error_message=message,
                stack_trace=trace,
                failure_classification=classification,
                source_artifact_id=source_artifact_id,
            )
        )
    return results


# pytest-playwright parametrizes browser_name, so a test id's trailing [...] starts with the
# engine — optionally followed by the test's own parametrize id (e.g. [chromium-case1]).
_ENGINES = ("chromium", "firefox", "webkit")


def _browser_from_name(name: str) -> str | None:
    match = re.search(r"\[([^\]]+)\]", name)
    if not match:
        return None
    engine = match.group(1).split("-", 1)[0]
    return engine if engine in _ENGINES else None


def _strip_browser_suffix(name: str) -> str:
    # Drop the engine token from the trailing id; keep any user parametrize id
    # ([chromium-case1] -> [case1]) so the displayed test name is not corrupted.
    def _repl(m: re.Match[str]) -> str:
        rest = m.group("rest")
        return f"[{rest}]" if rest else ""

    return re.sub(r"\[(?:chromium|firefox|webkit)(?:-(?P<rest>[^\]]*))?\]$", _repl, name)


def _seconds_to_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return round(float(value) * 1000)
    except ValueError:
        return None


def _resolve_artifact(
    classname: str, name: str, stem_to_artifact: dict[str, UUID | None]
) -> UUID | None:
    haystack = f"{classname} {name}"
    for stem, artifact_id in stem_to_artifact.items():
        if stem in haystack:
            return artifact_id
    return None


# ---------------------------------------------------------------------------
# Runner entry point
# ---------------------------------------------------------------------------


def run_scripts(
    *,
    scripts: list[ScriptToRun],
    base_url: str,
    browsers: list[BrowserSpec] | None = None,
    storage_state: dict[str, Any] | None = None,
    run_policy: str = "continue",
    wall_clock_timeout: int = 900,
    execution_timeout: int | None = None,
    headed: bool = False,
    capture_screenshots: bool = True,
    capture_traces: bool = True,
    base_env: dict[str, str] | None = None,
    server_mode: bool = False,
    workdir: str | None = None,
) -> RunResult:
    """Execute ``scripts`` against ``base_url`` across a browser matrix (Story 14.4).

    The subprocess call(s) are synchronous — the agent wraps this in ``asyncio.to_thread``.
    A separate pytest invocation runs per channel group (``--browser-channel`` is
    per-invocation); results merge into per-``(test, browser_label)`` records. When
    ``storage_state`` is set, the captured session is written into the transient temp dir
    and injected via a generated ``conftest.py`` — the blob never leaves the temp dir, which
    is deleted in ``finally`` (secret containment).
    """
    import os
    import shutil
    from datetime import UTC, datetime

    base_env = base_env if base_env is not None else dict(os.environ)
    # Strip any embedded basic-auth credentials before the URL touches the report/host/env.
    base_url = _strip_url_userinfo(base_url)
    host = urlsplit(base_url).netloc or base_url
    started_at = datetime.now(UTC).isoformat()
    specs = browsers if browsers else [BrowserSpec("chromium")]

    created_tmp = workdir is None
    tmp = workdir or tempfile.mkdtemp(prefix="jack_run_")
    tmp_path = Path(tmp)
    tmp_path.mkdir(parents=True, exist_ok=True)

    all_results: list[TestResult] = []
    produced_files: list[ProducedFile] = []
    log_chunks: list[str] = []
    unavailable: list[dict[str, str]] = []
    available: list[BrowserSpec] = []

    try:
        # Materialise scripts + isolated pytest.ini (no repo addopts/coverage).
        stem_to_artifact: dict[str, UUID | None] = {}
        for idx, script in enumerate(scripts):
            stem = f"test_{idx}_{safe_filename(script.name)}"
            stem_to_artifact[stem] = script.source_artifact_id
            (tmp_path / f"{stem}.py").write_text(script.content, encoding="utf-8")
        (tmp_path / "pytest.ini").write_text("[pytest]\naddopts =\n", encoding="utf-8")

        # Inject the captured session (AC3) — transient, never persisted/logged.
        if storage_state is not None:
            blob_path = tmp_path / "storage_state.json"
            blob_path.write_text(json.dumps(storage_state), encoding="utf-8")
            _write_storage_state_conftest(tmp_path, str(blob_path))

        available, unavailable = probe_browser_availability(specs)
        env = build_subprocess_env(base_env=base_env, base_url=base_url, server_mode=server_mode)

        for i, inv in enumerate(group_invocations(available)):
            inv_xml = str(tmp_path / f"results_{i}.xml")
            inv_out = str(tmp_path / "test-results" / f"inv_{i}")
            cmd = build_pytest_command(
                tmpdir=str(tmp_path),
                results_xml=inv_xml,
                engines=inv.engines,
                channel=inv.channel,
                headed=headed,
                run_policy=run_policy,
                output_dir=inv_out,
                capture_screenshots=capture_screenshots,
                capture_traces=capture_traces,
                per_test_timeout=execution_timeout,
            )
            stderr = ""
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(tmp_path),
                    capture_output=True,
                    timeout=wall_clock_timeout,
                    env=env,
                    check=False,
                )
                out = proc.stdout.decode(errors="replace") if proc.stdout else ""
                stderr = proc.stderr.decode(errors="replace") if proc.stderr else ""
            except subprocess.TimeoutExpired as exc:
                out = exc.stdout.decode(errors="replace") if exc.stdout else ""
                stderr = f"Execution timed out after {wall_clock_timeout}s."
            log_chunks.append(out + "\n" + stderr)

            all_results.extend(
                _collect_results(
                    results_xml=inv_xml,
                    scripts=scripts,
                    default_browser=inv.engines[0],
                    stem_to_artifact=stem_to_artifact,
                    stderr=stderr,
                    label_override=inv.label_override,
                )
            )
            produced_files.extend(
                _collect_output_files(inv_out, inv.label_override or inv.engines[0])
            )

        combined_log = scrub_secrets("\n".join(log_chunks)) or ""
        produced_files.insert(
            0, ProducedFile(name="run.log", content=combined_log.encode("utf-8"), kind="log")
        )

        completed_at = datetime.now(UTC).isoformat()
        summary = RunSummary(
            total=len(all_results),
            passed=sum(1 for r in all_results if r.status == STATUS_PASSED),
            failed=sum(1 for r in all_results if r.status == STATUS_FAILED),
            errors=sum(1 for r in all_results if r.status == STATUS_ERROR),
            skipped=sum(1 for r in all_results if r.status == STATUS_SKIPPED),
            duration_ms=_duration_ms(started_at, completed_at),
            browsers=[s.label for s in available],
            base_url_host=host,
            run_policy=run_policy,
            started_at=started_at,
            completed_at=completed_at,
            unavailable_browsers=unavailable,
        )
        return RunResult(
            results=all_results,
            summary=summary,
            produced_files=produced_files,
            stdout_tail=scrub_secrets("\n".join(log_chunks)[-8000:]) or "",
            stderr_tail="",
        )
    finally:
        # Always remove a runner-created temp dir (contains the storageState blob).
        if created_tmp:
            shutil.rmtree(tmp_path, ignore_errors=True)


def _collect_results(
    *,
    results_xml: str,
    scripts: list[ScriptToRun],
    default_browser: str,
    stem_to_artifact: dict[str, UUID | None],
    stderr: str,
    label_override: str | None = None,
) -> list[TestResult]:
    """Parse one invocation's JUnit XML; synthesize an error per script if it is missing.

    ``label_override`` (a channel label) overrides the engine-derived browser on every
    result — JUnit ids carry the engine ``[chromium]``, not the channel.
    """
    xml_path = Path(results_xml)
    results: list[TestResult]
    if xml_path.exists():
        try:
            results = parse_junit_xml(
                xml_path.read_text(encoding="utf-8"),
                default_browser=default_browser,
                stem_to_artifact=stem_to_artifact,
            )
        except ET.ParseError as exc:
            logger.warning("Could not parse JUnit XML: %s", exc)
            results = _synthesize_errors(scripts, label_override or default_browser, stderr)
        else:
            if label_override:
                for r in results:
                    r.browser = label_override
            return results
    else:
        results = _synthesize_errors(scripts, label_override or default_browser, stderr)
    return results


def _synthesize_errors(scripts: list[ScriptToRun], browser: str, stderr: str) -> list[TestResult]:
    """One error result per script when the subprocess produced no XML."""
    tail = scrub_secrets(stderr[-1000:]) or "Execution produced no results."
    return [
        TestResult(
            test_name=safe_filename(s.name),
            browser=browser,
            status=STATUS_ERROR,
            error_message="Script did not produce a result.",
            stack_trace=tail,
            failure_classification=CLASS_ERROR,
            source_artifact_id=s.source_artifact_id,
        )
        for s in scripts
    ]


def _collect_output_files(output_dir: str, browser: str) -> list[ProducedFile]:
    """Collect screenshots/traces pytest-playwright wrote under ``output_dir`` (14.3).

    Names are browser-aware and unique (the relative path joined by ``__``), so Story
    14.4 (multi-browser) reuses the same paths without change. Missing dir → ``[]``.
    """
    base = Path(output_dir)
    if not base.is_dir():
        return []
    collected: list[ProducedFile] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix == ".png":
            kind = "execution_screenshot"
        elif suffix == ".zip":
            kind = "trace"
        else:
            kind = "log"
        rel = path.relative_to(base).as_posix().replace("/", "__")
        name = rel if browser in rel else f"{path.stem}__{browser}{path.suffix}"
        collected.append(ProducedFile(name=name, content=path.read_bytes(), kind=kind))
    return collected


def _duration_ms(started_at: str, completed_at: str) -> int:
    from datetime import datetime

    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(completed_at)
        return max(0, int((end - start).total_seconds() * 1000))
    except ValueError:
        return 0
