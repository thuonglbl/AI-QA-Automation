"""Distill a browser-use run into a selector-rich, LLM-friendly action trace.

After the explorer drives the real app, ``browser_use`` records every action
together with the REAL DOM element it interacted with. We extract a compact
``[{action, params, element}]`` trace so the script generator can translate a
VERIFIED flow into a deterministic Playwright script using real selectors — no
invented locators.

The extractor is tolerant of the exact ``browser_use`` shape (the interacted
element may be a pydantic model, a dict, or a plain object) so it is unit-testable
with a lightweight fake history and resilient to minor library changes.
"""

import json
from typing import Any

# DOM attributes that make the best Playwright selectors (the LLM picks among them).
_USEFUL_ATTRS = (
    "data-testid",
    "data-test",
    "id",
    "name",
    "role",
    "aria-label",
    "placeholder",
    "type",
    "value",
    "title",
    "href",
    "alt",
)


def _serialize_element(element: Any) -> dict[str, Any] | None:
    """Reduce an interacted DOM element to the fields useful for selector choice."""
    if element is None:
        return None

    raw: dict[str, Any]
    if hasattr(element, "model_dump"):
        try:
            raw = element.model_dump()
        except Exception:
            raw = {}
    elif isinstance(element, dict):
        raw = dict(element)
    else:
        raw = {
            field: getattr(element, field)
            for field in ("node_name", "tag_name", "tag", "attributes", "x_path", "xpath", "text")
            if hasattr(element, field)
        }

    tag = raw.get("node_name") or raw.get("tag_name") or raw.get("tag")
    attributes = raw.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    selector_attrs = {
        name: attributes[name] for name in _USEFUL_ATTRS if attributes.get(name) not in (None, "")
    }
    text = raw.get("text") or raw.get("element_text")
    xpath = raw.get("x_path") or raw.get("xpath")

    out: dict[str, Any] = {}
    if tag:
        out["tag"] = str(tag).lower()
    if selector_attrs:
        out["attributes"] = selector_attrs
    if text:
        out["text"] = str(text).strip()[:120]
    if xpath:
        out["xpath"] = str(xpath)
    return out or None


def extract_trace(history: Any) -> list[dict[str, Any]]:
    """Distill a browser-use ``AgentHistoryList`` into ``[{action, params, element}]``.

    Uses ``history.model_actions()`` (each item is ``{<action_name>: {params},
    "interacted_element": <element|None>}``). Returns an empty list on any
    extraction failure so the caller can fall back gracefully.
    """
    steps: list[dict[str, Any]] = []
    try:
        actions = history.model_actions()
    except Exception:
        return steps
    if not isinstance(actions, list):
        return steps

    for action in actions:
        if not isinstance(action, dict):
            continue
        element = action.get("interacted_element")
        name = ""
        params: dict[str, Any] = {}
        for key, value in action.items():
            if key == "interacted_element":
                continue
            name = key
            params = value if isinstance(value, dict) else {"value": value}
            break
        if not name:
            continue
        steps.append({"action": name, "params": params, "element": _serialize_element(element)})
    return steps


def format_trace_for_prompt(trace: list[dict[str, Any]]) -> str:
    """Render a trace as pretty JSON for injection into the translation prompt."""
    return json.dumps(trace, indent=2, ensure_ascii=False, default=str)


__all__ = ["extract_trace", "format_trace_for_prompt"]
