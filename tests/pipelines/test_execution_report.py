"""Tests for the execution report composer (Story 14.5)."""

from __future__ import annotations

import json

from ai_qa.pipelines.execution_report import SCHEMA_VERSION, compose_execution_report

_SUMMARY = {
    "total": 3,
    "passed": 1,
    "failed": 1,
    "errors": 1,
    "skipped": 0,
    "duration_ms": 4200,
    "browsers": ["chromium", "firefox"],
    "unavailable_browsers": [{"label": "webkit", "reason": "not installed"}],
    "base_url_host": "app.example.com",
    "started_at": "2026-06-21T00:00:00+00:00",
    "completed_at": "2026-06-21T00:00:04+00:00",
}

_RESULTS = [
    {
        "test_name": "test_login",
        "browser": "chromium",
        "status": "passed",
        "duration_ms": 1200,
        "source_script_artifact_id": "script-1",
        "source_test_case_artifact_id": "tc-1",
    },
    {
        "test_name": "test_search",
        "browser": "chromium",
        "status": "failed",
        "duration_ms": 1500,
        "failure_classification": "assertion",
        "error_message": "AssertionError: not visible",
        "stack_trace": "expect(...).to_be_visible",
        "source_script_artifact_id": "script-2",
        "source_test_case_artifact_id": None,
    },
    {
        "test_name": "test_nav",
        "browser": "firefox",
        "status": "error",
        "duration_ms": 1500,
        "failure_classification": "navigation",
        "error_message": "net::ERR_CONNECTION_REFUSED",
        "source_script_artifact_id": "script-3",
    },
]

_ATTACHMENTS = {
    "test_search::chromium": {"screenshot_id": "shot-1", "trace_id": "trace-1", "log_id": "log-1"},
    # test_nav has no screenshot/trace — tolerated.
    "test_nav::firefox": {"screenshot_id": None, "trace_id": None, "log_id": "log-1"},
}


def test_report_contains_all_ac1_sections() -> None:
    md, structured = compose_execution_report(
        summary=_SUMMARY, results=_RESULTS, attachments=_ATTACHMENTS, run_id="run-abc"
    )
    assert "# Execution Report" in md
    assert "## Summary" in md
    assert "## Results" in md
    assert "## Failure Details" in md
    # Summary facts present.
    assert "run-abc" in md
    assert "app.example.com" in md
    assert "chromium, firefox" in md
    assert "Success rate: 33.3%" in md
    # Unavailable browser surfaced (AC2-ish reporting).
    assert "webkit" in md
    # Per-test table rows.
    assert "test_login" in md
    assert "test_search" in md
    # Linked attachments where present, placeholders where missing.
    assert "artifact:shot-1" in md
    assert "(no screenshot)" in md  # test_nav has no screenshot
    assert "artifact:script-2" in md  # linked source script

    # Structured payload.
    assert structured["schema_version"] == SCHEMA_VERSION
    assert structured["run_id"] == "run-abc"
    assert structured["summary"]["success_rate"] == 33.3
    assert len(structured["results"]) == 3
    assert structured["attachments"] == _ATTACHMENTS
    # round-trips as JSON (Jack persists json.dumps of this)
    json.dumps(structured, default=str)


def test_report_tolerates_missing_attachments_and_provenance() -> None:
    """A result with no attachments/provenance never raises and renders placeholders."""
    results = [
        {
            "test_name": "test_x",
            "browser": "chromium",
            "status": "failed",
            "error_message": "boom",
        }
    ]
    md, structured = compose_execution_report(
        summary={"total": 1, "failed": 1}, results=results, attachments={}, run_id="r"
    )
    assert "(no screenshot)" in md
    assert "(no script)" in md
    assert "(test case)" not in md  # the link is "(no test case)"
    assert "(no test case)" in md
    assert structured["results"][0]["attachments"] == {}


def test_report_empty_results_is_valid() -> None:
    """An all-unavailable run produces a valid 'no results' report, not a crash."""
    md, structured = compose_execution_report(
        summary={
            "total": 0,
            "browsers": [],
            "unavailable_browsers": [{"label": "chromium", "reason": "x"}],
        },
        results=[],
        attachments={},
        run_id="r",
    )
    assert "No results" in md
    assert structured["results"] == []
    assert structured["summary"]["total"] == 0


def test_report_table_uses_spaced_separators() -> None:
    """MD060: table column separators must be spaced (e.g. '| ---- |')."""
    md, _ = compose_execution_report(
        summary=_SUMMARY, results=_RESULTS, attachments=_ATTACHMENTS, run_id="r"
    )
    assert "| ---- | ------- | ------ | -------- | ------- |" in md
    # MD036: section titles are real headings, not bold-as-heading.
    assert "**Summary**" not in md


def test_composer_secret_handling_is_a_documented_passthrough() -> None:
    """Leak-canary boundary: the composer renders error/stack fields VERBATIM — scrubbing is
    the runner's job (parse_junit_xml, covered by test_script_runner). This pins the contract:
    (1) a recognizable token in the inputs is not silently dropped, and (2) the composer adds
    no NEW credential-shaped text of its own to already-scrubbed inputs.
    """
    canary = "SECRET-CANARY-aB3xK"
    results = [
        {
            "test_name": "test_x",
            "browser": "chromium",
            "status": "failed",
            "error_message": f"boom {canary}",
            "stack_trace": f"trace {canary}",
        }
    ]
    md, structured = compose_execution_report(
        summary={"total": 1, "failed": 1}, results=results, attachments={}, run_id="r"
    )
    # The canary flows through unchanged — scrubbing is upstream, by design.
    assert canary in md + json.dumps(structured, default=str)
    # Composing clean inputs introduces no credential-shaped text.
    clean_md, clean_structured = compose_execution_report(
        summary=_SUMMARY, results=_RESULTS, attachments=_ATTACHMENTS, run_id="r"
    )
    clean_blob = (clean_md + json.dumps(clean_structured, default=str)).lower()
    assert "password" not in clean_blob
    assert "sk-" not in clean_blob


def test_report_role_column_and_attachment_keys_avoid_cross_role_collision() -> None:
    """Slice 6: same (test, browser) under two roles renders distinctly and resolves each
    role's own attachment via the role-aware key (no last-write-wins collision)."""
    results = [
        {
            "test_name": "test_login",
            "browser": "chromium",
            "status": "failed",
            "role": "Admin",
            "error_message": "a",
        },
        {
            "test_name": "test_login",
            "browser": "chromium",
            "status": "failed",
            "role": "User",
            "error_message": "b",
        },
    ]
    attachments = {
        "Admin::test_login::chromium": {"screenshot_id": "shot-admin"},
        "User::test_login::chromium": {"screenshot_id": "shot-user"},
    }
    md, structured = compose_execution_report(
        summary={"total": 2, "failed": 2}, results=results, attachments=attachments, run_id="r"
    )
    assert "| Test | Browser | Role |" in md
    assert "Admin" in md and "User" in md
    by_role = {r["role"]: r["attachments"] for r in structured["results"]}
    assert by_role["Admin"]["screenshot_id"] == "shot-admin"
    assert by_role["User"]["screenshot_id"] == "shot-user"
