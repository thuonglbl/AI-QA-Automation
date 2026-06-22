"""Tests for browser-use trace extraction (browser/trace.py).

Uses a lightweight fake history (mirroring browser_use's ``model_actions()``
shape) so the extractor is verified offline. The interacted element is exercised
as a plain object, a dict, and a pydantic-like ``model_dump`` object.
"""

import json
from typing import Any

from ai_qa.browser.trace import extract_trace, format_trace_for_prompt


class _AttrElement:
    """Plain-object interacted element (attribute access)."""

    def __init__(self) -> None:
        self.node_name = "BUTTON"
        self.attributes = {"data-testid": "login-submit", "role": "button", "aria-label": "Log in"}
        self.x_path = "//button[@id='go']"


class _DumpElement:
    """pydantic-like element exposing model_dump()."""

    def model_dump(self) -> dict[str, Any]:
        return {
            "tag_name": "INPUT",
            "attributes": {"name": "q", "placeholder": "Search", "type": "text"},
            "xpath": "//input[1]",
        }


class _FakeHistory:
    def __init__(self, actions: list[dict[str, Any]]) -> None:
        self._actions = actions

    def model_actions(self) -> list[dict[str, Any]]:
        return self._actions


def test_extract_trace_distills_actions_and_real_selectors() -> None:
    history = _FakeHistory(
        [
            {"go_to_url": {"url": "https://app.test/login"}, "interacted_element": None},
            {"click_element_by_index": {"index": 5}, "interacted_element": _AttrElement()},
            {
                "input_text": {"index": 3, "text": "hello"},
                "interacted_element": {
                    "node_name": "INPUT",
                    "attributes": {"name": "q", "placeholder": "Search"},
                },
            },
        ]
    )

    trace = extract_trace(history)

    assert len(trace) == 3
    # Navigation: no element.
    assert trace[0]["action"] == "go_to_url"
    assert trace[0]["params"]["url"] == "https://app.test/login"
    assert trace[0]["element"] is None
    # Click: real button selector recovered (object element).
    assert trace[1]["action"] == "click_element_by_index"
    assert trace[1]["element"]["tag"] == "button"
    assert trace[1]["element"]["attributes"]["data-testid"] == "login-submit"
    assert trace[1]["element"]["attributes"]["aria-label"] == "Log in"
    assert trace[1]["element"]["xpath"] == "//button[@id='go']"
    # Input: dict element, params carried.
    assert trace[2]["action"] == "input_text"
    assert trace[2]["params"]["text"] == "hello"
    assert trace[2]["element"]["attributes"]["placeholder"] == "Search"


def test_extract_trace_handles_model_dump_element() -> None:
    history = _FakeHistory(
        [{"click_element_by_index": {"index": 1}, "interacted_element": _DumpElement()}]
    )
    trace = extract_trace(history)
    assert trace[0]["element"]["tag"] == "input"
    assert trace[0]["element"]["attributes"]["name"] == "q"
    assert trace[0]["element"]["xpath"] == "//input[1]"


def test_extract_trace_returns_empty_on_failure() -> None:
    class _Broken:
        def model_actions(self) -> list[dict[str, Any]]:
            raise RuntimeError("history unavailable")

    assert extract_trace(_Broken()) == []


def test_format_trace_for_prompt_is_json() -> None:
    trace = [{"action": "go_to_url", "params": {"url": "x"}, "element": None}]
    rendered = format_trace_for_prompt(trace)
    assert json.loads(rendered) == trace
