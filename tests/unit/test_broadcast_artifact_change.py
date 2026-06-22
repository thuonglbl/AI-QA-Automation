"""Unit tests for ArtifactChangeEvent payload and broadcast_artifact_change membership scope.

Story 10.6 — Tasks 3.4 and 3.5.

3.4: Verifies ArtifactChangeEvent serialisation contains all AC1-required fields.
3.5: Verifies broadcast_artifact_change delivers only to connections where the
     connected user is a member of the changed project (membership-set routing).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_qa.models import ArtifactChangeEvent

# ---------------------------------------------------------------------------
# Task 3.4 — ArtifactChangeEvent payload unit test
# ---------------------------------------------------------------------------


def test_artifact_change_event_payload_contains_all_ac1_fields() -> None:
    """AC1: ArtifactChangeEvent serialisation must include all required fields.

    Fields required by AC1: type, project_id, artifact_id, change_type, timestamp.
    """
    event = ArtifactChangeEvent(
        project_id="proj-123",
        artifact_id="art-456",
        change_type="created",  # type: ignore[arg-type]
    )

    data = event.model_dump()

    assert data["type"] == "artifact_change", "type field must be 'artifact_change'"
    assert data["project_id"] == "proj-123", "project_id must be present"
    assert data["artifact_id"] == "art-456", "artifact_id must be present"
    assert data["change_type"] == "created", "change_type must be present"
    assert "timestamp" in data, "timestamp must be present"
    assert data["timestamp"] is not None, "timestamp must not be None"


def test_artifact_change_event_json_serialisation_contains_all_ac1_fields() -> None:
    """AC1: ArtifactChangeEvent JSON serialisation must include all required fields."""
    import json

    event = ArtifactChangeEvent(
        project_id="proj-123",
        artifact_id="art-456",
        change_type="updated",  # type: ignore[arg-type]
    )

    json_str = event.model_dump_json()
    data = json.loads(json_str)

    assert data["type"] == "artifact_change"
    assert data["project_id"] == "proj-123"
    assert data["artifact_id"] == "art-456"
    assert data["change_type"] == "updated"
    assert "timestamp" in data


# ---------------------------------------------------------------------------
# Task 3.5 — broadcast_artifact_change membership-scope unit test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_artifact_change_delivers_only_to_project_members() -> None:
    """AC3: broadcast_artifact_change delivers only to connections where the
    connected user is a member of the changed project.

    Directly manipulates active_connections with two fake entries:
    - member_conn: member_project_ids CONTAINS the target project
    - outsider_conn: member_project_ids does NOT contain the target project

    Asserts only the member connection receives the JSON payload.
    """
    import ai_qa.api.websocket as ws_module

    project_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    other_project_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    member_ws = MagicMock()
    member_ws.send_text = AsyncMock()

    outsider_ws = MagicMock()
    outsider_ws.send_text = AsyncMock()

    # Snapshot and restore active_connections to avoid polluting other tests
    original_connections = dict(ws_module.active_connections)
    try:
        ws_module.active_connections["member-conn"] = (
            member_ws,
            None,
            None,
            None,
            frozenset({project_id}),
        )
        ws_module.active_connections["outsider-conn"] = (
            outsider_ws,
            None,
            None,
            None,
            frozenset({other_project_id}),
        )

        await ws_module.broadcast_artifact_change(
            project_id=project_id,
            artifact_id="art-id",
            change_type="created",
        )
    finally:
        ws_module.active_connections.clear()
        ws_module.active_connections.update(original_connections)

    member_ws.send_text.assert_awaited_once()
    outsider_ws.send_text.assert_not_awaited()

    # Verify the payload sent to the member is valid JSON with correct fields
    import json

    sent_payload = json.loads(member_ws.send_text.call_args.args[0])
    assert sent_payload["type"] == "artifact_change"
    assert sent_payload["project_id"] == project_id
    assert sent_payload["artifact_id"] == "art-id"
    assert sent_payload["change_type"] == "created"


@pytest.mark.asyncio
async def test_broadcast_artifact_change_empty_membership_receives_nothing() -> None:
    """AC3: A connection with an empty member_project_ids frozenset receives no events."""
    import ai_qa.api.websocket as ws_module

    project_id = "cccccccc-cccc-cccc-cccc-cccccccccccc"

    no_membership_ws = MagicMock()
    no_membership_ws.send_text = AsyncMock()

    original_connections = dict(ws_module.active_connections)
    try:
        ws_module.active_connections["no-membership-conn"] = (
            no_membership_ws,
            None,
            None,
            None,
            frozenset(),  # no memberships
        )

        await ws_module.broadcast_artifact_change(
            project_id=project_id,
            artifact_id="art-id",
            change_type="deleted",
        )
    finally:
        ws_module.active_connections.clear()
        ws_module.active_connections.update(original_connections)

    no_membership_ws.send_text.assert_not_awaited()
