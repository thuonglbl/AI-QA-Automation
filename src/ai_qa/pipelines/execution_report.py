"""Execution report composer (Story 14.5).

Pure/testable: takes the structured results (14.2/14.4) + the persisted attachment link
map (14.3) and produces ``(markdown, structured_json)``. The agent persists
``report.md`` (``kind="report"``, visible in Reports) + ``report.json``
(``kind="configuration"``, hidden companion holding the attachment link map for the
14.6 drilldown) — mirroring Bob's ``requirement.md`` + ``requirement.metadata.json``.

Hard rules: faithful + complete (never omit failures or fabricate passes), tolerant of
missing attachments / empty result sets (never raises), and consumes only already-scrubbed
fields (no secrets re-introduced).
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = 1


def attachment_key(test_name: str, browser: str, role: str | None = None) -> str:
    """Stable attachment-map key.

    Includes role so the same (test, browser) running under different roles (Slice 6
    role-grouped runs) never collides. This format MUST stay byte-identical with the key
    Jack builds (``agents/jack.py``) and the frontend lookup (``JackExecutionReport.tsx``).
    """
    if role:
        return f"{role}::{test_name}::{browser}"
    return f"{test_name}::{browser}"


def _link(artifact_id: Any, label: str) -> str:
    """Render an attachment/provenance link, or a tolerant placeholder when absent."""
    if not artifact_id:
        return f"(no {label})"
    return f"[{label}](artifact:{artifact_id})"


def _md_escape(text: str) -> str:
    """Escape pipe characters so a value never breaks a Markdown table row."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def compose_execution_report(
    *,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    attachments: dict[str, dict[str, Any]],
    run_id: Any,
) -> tuple[str, dict[str, Any]]:
    """Compose ``(markdown, structured_json)`` from execution results (AC1/AC2).

    ``attachments`` maps ``f"{test}::{browser}"`` → ``{screenshot_id, trace_id, log_id}``
    (any may be missing/None). ``results`` are per-``(test, browser)`` dicts with status,
    duration, classification, scrubbed error/stack, and provenance ids.
    """
    total = int(summary.get("total", len(results)))
    passed = int(summary.get("passed", 0))
    failed = int(summary.get("failed", 0))
    errors = int(summary.get("errors", 0))
    skipped = int(summary.get("skipped", 0))
    duration_ms = int(summary.get("duration_ms", 0))
    browsers = summary.get("browsers") or []
    unavailable = summary.get("unavailable_browsers") or []
    success_rate = round((passed / total) * 100, 1) if total else 0.0

    lines: list[str] = []
    lines.append("<!-- markdownlint-disable MD033 MD041 -->")
    lines.append("# Execution Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Run id: {run_id}")
    lines.append(f"- Started: {summary.get('started_at', '(unknown)')}")
    lines.append(f"- Completed: {summary.get('completed_at', '(unknown)')}")
    lines.append(f"- Duration: {duration_ms / 1000:.1f}s")
    lines.append(f"- Environment host: {summary.get('base_url_host', '(unknown)')}")
    lines.append(f"- Browsers: {', '.join(browsers) if browsers else '(none)'}")
    lines.append(
        f"- Totals: {total} total · {passed} passed · {failed} failed · "
        f"{errors} error(s) · {skipped} skipped"
    )
    lines.append(f"- Success rate: {success_rate}%")
    if unavailable:
        rendered = ", ".join(
            f"{u.get('label', '?')} ({u.get('reason', 'unavailable')})" for u in unavailable
        )
        lines.append(f"- Unavailable browsers: {rendered}")
    lines.append("")

    lines.append("## Results")
    lines.append("")
    if not results:
        lines.append("_No results — no browser was available to run, or no scripts ran._")
        lines.append("")
    else:
        any_role = any(r.get("role") for r in results)
        if any_role:
            lines.append("| Test | Browser | Role | Status | Duration | Failure |")
            lines.append("| ---- | ------- | ---- | ------ | -------- | ------- |")
        else:
            lines.append("| Test | Browser | Status | Duration | Failure |")
            lines.append("| ---- | ------- | ------ | -------- | ------- |")
        for r in results:
            dur = r.get("duration_ms")
            dur_s = f"{dur / 1000:.2f}s" if isinstance(dur, int | float) else "-"
            fail = _md_escape(str(r.get("failure_classification") or ""))
            row = (
                f"| {_md_escape(str(r.get('test_name', '')))} "
                f"| {_md_escape(str(r.get('browser', '')))} "
            )
            if any_role:
                row += f"| {_md_escape(str(r.get('role') or '-'))} "
            row += f"| {r.get('status', '')} | {dur_s} | {fail or '-'} |"
            lines.append(row)
        lines.append("")

    # Per-failure detail blocks (failed/error only).
    failures = [r for r in results if r.get("status") in ("failed", "error")]
    if failures:
        lines.append("## Failure Details")
        lines.append("")
        for r in failures:
            role = r.get("role")
            key = attachment_key(str(r.get("test_name", "")), str(r.get("browser", "")), role)
            att = attachments.get(key, {})
            heading_role = f" · {role}" if role else ""
            lines.append(f"### {r.get('test_name', '')} [{r.get('browser', '')}{heading_role}]")
            lines.append("")
            lines.append(f"- Classification: {r.get('failure_classification') or '(none)'}")
            lines.append(f"- Error: {_md_escape(str(r.get('error_message') or '(none)'))}")
            lines.append(f"- Script: {_link(r.get('source_script_artifact_id'), 'script')}")
            lines.append(
                f"- Source test case: {_link(r.get('source_test_case_artifact_id'), 'test case')}"
            )
            lines.append(f"- Screenshot: {_link(att.get('screenshot_id'), 'screenshot')}")
            lines.append(f"- Trace: {_link(att.get('trace_id'), 'trace')}")
            lines.append(f"- Log: {_link(att.get('log_id'), 'log')}")
            stack = r.get("stack_trace")
            if stack:
                lines.append("")
                lines.append("```")
                lines.append(_md_escape_block(str(stack)))
                lines.append("```")
            lines.append("")

    markdown = "\n".join(lines).rstrip() + "\n"

    structured: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(run_id),
        "summary": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "duration_ms": duration_ms,
            "success_rate": success_rate,
            "browsers": list(browsers),
            "unavailable_browsers": list(unavailable),
            "base_url_host": summary.get("base_url_host"),
            "started_at": summary.get("started_at"),
            "completed_at": summary.get("completed_at"),
        },
        "results": [
            {
                "test_name": r.get("test_name"),
                "browser": r.get("browser"),
                "role": r.get("role"),
                "status": r.get("status"),
                "duration_ms": r.get("duration_ms"),
                "failure_classification": r.get("failure_classification"),
                "error_message": r.get("error_message"),
                "stack_trace": r.get("stack_trace"),
                "source_script_artifact_id": _str_or_none(r.get("source_script_artifact_id")),
                "source_test_case_artifact_id": _str_or_none(r.get("source_test_case_artifact_id")),
                "attachments": attachments.get(
                    attachment_key(
                        str(r.get("test_name", "")), str(r.get("browser", "")), r.get("role")
                    ),
                    {},
                ),
            }
            for r in results
        ],
        "attachments": attachments,
    }
    return markdown, structured


def _md_escape_block(text: str) -> str:
    """Keep a fenced code block from breaking out (strip backtick fences in the body)."""
    return text.replace("```", "ʼʼʼ")


def _str_or_none(value: Any) -> str | None:
    return str(value) if value else None
