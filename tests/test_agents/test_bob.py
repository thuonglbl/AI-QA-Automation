import asyncio
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_qa.agents.base import AgentState
from ai_qa.agents.bob import _MAX_CLARIFY_ROUNDS, BobAgent
from ai_qa.exceptions import MCPConnectionError, PipelineError
from ai_qa.models import StageResult
from ai_qa.pipelines.models import JiraIssue
from ai_qa.secrets.service import SecretStatus


@pytest.fixture
def bob_agent(mock_project_context: MagicMock) -> BobAgent:
    agent = BobAgent(
        name="Bob", color="#2196F3", step_number=3, step_title="Requirements Extraction"
    )
    agent.set_project_context(mock_project_context)
    return agent


@pytest.mark.asyncio
async def test_bob_initial_process_with_requirement_page(bob_agent: BobAgent) -> None:
    """Test process() uses the requirement page URL if found via find_parent_pages."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceURLParser") as mock_parser_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
    ):
        mock_mcp_client = AsyncMock()
        mock_mcp_client_class.return_value = mock_mcp_client

        mock_parser = mock_parser_class.return_value
        mock_parser.extract_page_id.return_value = None
        mock_parser.extract_space_key.return_value = "TEST"

        mock_reader = AsyncMock()
        mock_reader.find_parent_pages.return_value = StageResult(
            success=True,
            data=[
                MagicMock(
                    url="https://company.atlassian.net/wiki/spaces/TEST/pages/123/Requirements"
                )
            ],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent.process(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "confirm_parent"
        # Verify it used the suggested requirement page URL instead of the base URL
        assert (
            result.data["suggested_page"]
            == "https://company.atlassian.net/wiki/spaces/TEST/pages/123/Requirements"
        )


@pytest.mark.asyncio
async def test_bob_initial_process_fallback_to_confluence_url(bob_agent: BobAgent) -> None:
    """Test process() falls back to the original URL if no requirement page is found."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceURLParser") as mock_parser_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
    ):
        mock_mcp_client = AsyncMock()
        mock_mcp_client_class.return_value = mock_mcp_client

        mock_parser = mock_parser_class.return_value
        mock_parser.extract_page_id.return_value = None
        mock_parser.extract_space_key.return_value = "TEST"

        mock_reader = AsyncMock()
        # Simulate no requirement page found
        mock_reader.find_parent_pages.return_value = StageResult(
            success=True,
            data=[],
            errors=[],
            warnings=[],
            confidence=0.0,
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent.process(input_data)

        assert result.success is True
        assert result.data is not None
        assert result.data["type"] == "confirm_parent"
        # Verify it fell back to the original input URL
        assert result.data["suggested_page"] == input_data["confluence_url"]


def test_bob_auto_save_requirements_saves_every_page(bob_agent: BobAgent) -> None:
    """Per-page review removed: every extracted page is auto-saved as an approved requirement."""
    bob_agent.pages = [
        {
            "page_id": "1",
            "page_title": "P1",
            "source_url": "https://example.com/p1",
            "source_type": "confluence",
            "requirement_md": "# R1",
            "quality_issues": [],
        },
        {
            "page_id": "2",
            "page_title": "P2",
            "source_url": "https://example.com/p2",
            "source_type": "confluence",
            "requirement_md": "# R2",
            "quality_issues": [],
        },
    ]

    with patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class:
        mock_adapter = mock_adapter_class.return_value
        saved = bob_agent._auto_save_requirements()

    assert saved == 2
    assert mock_adapter.save_requirement.call_count == 2
    assert mock_adapter.delete_draft_requirement.call_count == 2
    assert bob_agent._resolved_page_ids == {"1", "2"}


def test_bob_auto_save_requirements_skips_failed_conversion(bob_agent: BobAgent) -> None:
    """Pages whose LLM conversion produced empty markdown are skipped, not saved."""
    bob_agent.pages = [
        {"page_id": "1", "source_url": "u", "requirement_md": "", "quality_issues": []},
        {"page_id": "2", "source_url": "u", "requirement_md": "# ok", "quality_issues": []},
    ]
    with patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class:
        mock_adapter = mock_adapter_class.return_value
        saved = bob_agent._auto_save_requirements()
    assert saved == 1
    assert mock_adapter.save_requirement.call_count == 1
    assert bob_agent._resolved_page_ids == {"2"}


@pytest.mark.asyncio
async def test_bob_handle_select_id_confluence_reuse(bob_agent: BobAgent) -> None:
    """Selecting an already-extracted Confluence page id reuses it (no re-read) and goes DONE."""
    bob_agent.phase = "select_id"
    bob_agent.pages = [
        {
            "page_id": "12345",
            "page_title": "P",
            "source_url": "https://example.com/p",
            "source_type": "confluence",
            "requirement_md": "# R",
            "quality_issues": [],
        }
    ]

    with (
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
        patch("ai_qa.agents.bob.JiraReader") as mock_jira,
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message"),
    ):
        mock_adapter = mock_adapter_class.return_value
        await bob_agent.handle_approve({"action": "select_id", "id": "12345"})

    mock_jira.assert_not_called()  # already-saved Confluence page → no re-read
    mock_adapter.save_metadata.assert_called_once()
    name, payload = mock_adapter.save_metadata.call_args[0]
    assert name == "mary_selected_id.json"
    assert payload["selected_id"] == "12345"
    assert payload["source_type"] == "confluence"
    assert bob_agent._selected_id == "12345"
    mock_transition.assert_called_with(AgentState.DONE)


@pytest.mark.asyncio
async def test_bob_handle_select_id_jira_reads_and_saves(bob_agent: BobAgent) -> None:
    """Selecting a Jira ticket id (not already extracted) reads+saves it, then goes DONE."""
    bob_agent.phase = "select_id"
    bob_agent.pages = []

    with (
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
        patch.object(
            bob_agent, "_read_and_save_jira_ticket", new=AsyncMock(return_value=True)
        ) as mock_read,
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message"),
    ):
        mock_adapter = mock_adapter_class.return_value
        await bob_agent.handle_approve({"action": "select_id", "id": "CORP_PT_TOOL-1635"})

    mock_read.assert_awaited_once()
    _, payload = mock_adapter.save_metadata.call_args[0]
    assert payload["selected_id"] == "CORP_PT_TOOL-1635"
    assert payload["source_type"] == "jira"
    mock_transition.assert_called_with(AgentState.DONE)


@pytest.mark.asyncio
async def test_bob_handle_select_id_unknown_id_stays(bob_agent: BobAgent) -> None:
    """An id that is neither a Jira key nor an extracted Confluence page → error, no DONE."""
    bob_agent.phase = "select_id"
    bob_agent.pages = [{"page_id": "999", "requirement_md": "# R", "quality_issues": []}]

    with (
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        mock_adapter = mock_adapter_class.return_value
        await bob_agent.handle_approve({"action": "select_id", "id": "12345"})

    mock_adapter.save_metadata.assert_not_called()
    assert all(AgentState.DONE not in c.args for c in mock_transition.call_args_list)
    assert any(c.kwargs.get("message_type") == "error" for c in mock_send.call_args_list)


@pytest.mark.asyncio
async def test_bob_handle_select_id_blank_skips_to_sarah(bob_agent: BobAgent) -> None:
    """A blank id skips test-case generation: Bob goes DONE with skip_to_sarah and
    persists no selection (Mary is bypassed; Sarah reuses existing test cases)."""
    bob_agent.phase = "select_id"
    bob_agent.pages = [{"page_id": "12345", "requirement_md": "# R", "quality_issues": []}]

    with (
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        await bob_agent.handle_approve({"action": "select_id", "id": ""})

    # No adapter work, no selection persisted — Mary never runs.
    mock_adapter_class.assert_not_called()
    # Bob completed and handed off.
    mock_transition.assert_called_with(AgentState.DONE)
    assert bob_agent.phase == "done"
    # The handoff message carries skip_to_sarah so the frontend routes to Sarah.
    assert any(
        (c.kwargs.get("metadata") or {}).get("skip_to_sarah") for c in mock_send.call_args_list
    )
    assert all(c.kwargs.get("message_type") != "error" for c in mock_send.call_args_list)


@pytest.mark.asyncio
async def test_bob_extract_descendants_creates_single_mcp_client(bob_agent: BobAgent) -> None:
    """AC2: _extract_descendants must create only ONE MCPClient (not open a new connection)."""
    bob_agent._page_id = "12345"
    bob_agent._space_key = "TEST"

    # Configure project mock to return a Project-like object with confluence_base_url
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    mock_client = AsyncMock()
    mock_client.is_connected = True

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter"),
        patch("ai_qa.agents.bob.ContentParser"),
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config") as mock_llm_config,
    ):
        mock_llm_config.return_value = MagicMock()
        mock_mcp_client_class.return_value = mock_client

        # Return empty list for children so it exits gracefully with "no pages" error
        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True,
            data=[],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=False, data=None, errors=["mock failure"], warnings=[], confidence=0.0
        )
        mock_reader_class.return_value = mock_reader

        # Call extract_descendants — should fail gracefully with no pages
        await bob_agent._extract_descendants("Test Parent")

        # MCPClient should only be instantiated ONCE
        assert mock_mcp_client_class.call_count == 1


_VALID_CONFLUENCE_URL = "https://company.atlassian.net/wiki/spaces/TEST/pages/12345/Title"


@pytest.mark.asyncio
@patch("ai_qa.agents.bob.MCPClient")
@patch("ai_qa.agents.bob.ConfluenceReader")
async def test_bob_handle_start_confirm_parent(
    mock_reader_class: MagicMock, mock_mcp_client_class: MagicMock, bob_agent: BobAgent
) -> None:
    """Test handle_start when process returns confirm_parent."""
    mock_reader_class.return_value.check_tool_availability = AsyncMock(return_value=[])
    mock_mcp_client_class.return_value.connect = AsyncMock()
    mock_mcp_client_class.return_value.disconnect = AsyncMock()
    with patch.object(bob_agent, "process") as mock_process:
        mock_process.return_value = StageResult(
            success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
        )
        await bob_agent.handle_start({"confluence_url": _VALID_CONFLUENCE_URL})
        assert bob_agent.phase == "confirm_parent"
        assert bob_agent.state == AgentState.REVIEW_REQUEST


@pytest.mark.asyncio
@patch("ai_qa.agents.bob.MCPClient")
@patch("ai_qa.agents.bob.ConfluenceReader")
async def test_bob_handle_start_review_markdown(
    mock_reader_class: MagicMock, mock_mcp_client_class: MagicMock, bob_agent: BobAgent
) -> None:
    """Test handle_start when pages are successfully processed."""
    mock_reader_class.return_value.check_tool_availability = AsyncMock(return_value=[])
    mock_mcp_client_class.return_value.connect = AsyncMock()
    mock_mcp_client_class.return_value.disconnect = AsyncMock()
    with patch.object(bob_agent, "process") as mock_process:
        mock_process.return_value = StageResult(success=True)
        bob_agent.pages = [{"title": "Page 1"}]
        await bob_agent.handle_start({"confluence_url": _VALID_CONFLUENCE_URL})
        assert bob_agent.phase == "review_markdown"
        assert bob_agent.state == AgentState.REVIEW_REQUEST


@pytest.mark.asyncio
@patch("ai_qa.agents.bob.MCPClient")
@patch("ai_qa.agents.bob.ConfluenceReader")
async def test_bob_handle_start_error(
    mock_reader_class: MagicMock, mock_mcp_client_class: MagicMock, bob_agent: BobAgent
) -> None:
    """Test handle_start when process raises an exception."""
    mock_reader_class.return_value.check_tool_availability = AsyncMock(return_value=[])
    mock_mcp_client_class.return_value.connect = AsyncMock()
    mock_mcp_client_class.return_value.disconnect = AsyncMock()
    with patch.object(bob_agent, "process") as mock_process:
        mock_process.side_effect = Exception("Crash")
        await bob_agent.handle_start({"confluence_url": _VALID_CONFLUENCE_URL})
        assert bob_agent.state == AgentState.ERROR


@pytest.mark.asyncio
async def test_bob_process_with_feedback(bob_agent: BobAgent) -> None:
    """process(feedback) re-runs RequirementFormatter on raw_html and returns revised md."""
    bob_agent.pages = [
        {
            "page_id": "1",
            "page_title": "Page 1",
            "source_url": "https://example.com/p1",
            "raw_html": "<p>source html</p>",
            "requirement_md": "# Old",
            "quality_issues": [],
        }
    ]
    bob_agent.current_page_index = 0

    mock_formatter = AsyncMock()
    mock_formatter.convert_page = AsyncMock(return_value="# Revised")

    with (
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.LLMClient"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
        patch.object(bob_agent, "send_message"),
    ):
        result = await bob_agent.process({}, feedback="Fix X")

    assert result.success is True
    assert result.data is not None
    assert result.data["requirement_md"] == "# Revised"
    mock_formatter.convert_page.assert_awaited_once()
    _, kwargs = mock_formatter.convert_page.call_args
    assert kwargs.get("feedback") == "Fix X"


@pytest.mark.asyncio
async def test_bob_process_feedback_no_raw_html_falls_back(bob_agent: BobAgent) -> None:
    """page with raw_html='' (Jira-style) → returns page unchanged, no RequirementFormatter."""
    bob_agent.pages = [
        {
            "page_id": "PROJ-1",
            "page_title": "[PROJ-1] Jira Ticket",
            "source_url": "https://jira.example.com/PROJ-1",
            "raw_html": "",
            "requirement_md": "# Jira",
            "source_type": "jira",
            "quality_issues": [],
        }
    ]
    bob_agent.current_page_index = 0

    with (
        patch("ai_qa.agents.bob.RequirementFormatter") as mock_fmt_class,
        patch.object(bob_agent, "send_message"),
    ):
        result = await bob_agent.process({}, feedback="Add preconditions")

    assert result.success is True
    assert result.data is not None
    assert result.data["requirement_md"] == "# Jira"  # unchanged
    mock_fmt_class.assert_not_called()


@pytest.mark.asyncio
async def test_bob_process_feedback_llm_error_falls_back(bob_agent: BobAgent) -> None:
    """LLM error during reprocess → success=True, page unchanged, warning sent, no raise."""
    bob_agent.pages = [
        {
            "page_id": "1",
            "page_title": "P1",
            "source_url": "https://example.com/p1",
            "raw_html": "<p>html</p>",
            "requirement_md": "# Original",
            "quality_issues": [],
        }
    ]
    bob_agent.current_page_index = 0

    mock_formatter = AsyncMock()
    mock_formatter.convert_page = AsyncMock(side_effect=RuntimeError("LLM failure"))

    with (
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.LLMClient"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        result = await bob_agent.process({}, feedback="Fix it")

    assert result.success is True
    assert result.data is not None
    assert result.data["requirement_md"] == "# Original"  # unchanged after LLM error
    warning_calls = [c for c in mock_send.call_args_list if "warning" in str(c)]
    assert len(warning_calls) > 0


@pytest.mark.asyncio
async def test_bob_handle_reject_targets_page_and_re_presents(bob_agent: BobAgent) -> None:
    """handle_reject targets by page_id, acks BEFORE processing, re-emits is_review_ready."""
    p1 = {
        "page_id": "1",
        "page_title": "P1",
        "source_url": "https://example.com/p1",
        "raw_html": "<p>a</p>",
        "requirement_md": "# P1",
        "quality_issues": [],
    }
    p2 = {
        "page_id": "2",
        "page_title": "P2",
        "source_url": "https://example.com/p2",
        "raw_html": "<p>b</p>",
        "requirement_md": "# P2",
        "quality_issues": [],
    }
    bob_agent.pages = [p1, p2]
    bob_agent.current_page_index = 0

    updated_p2 = {**p2, "requirement_md": "# P2 Revised"}
    mock_process = AsyncMock(
        return_value=StageResult(
            success=True, data=updated_p2, errors=[], warnings=[], confidence=1.0
        )
    )

    send_calls: list[tuple[str, str]] = []

    async def capture_send(content: str, message_type: str = "text", **_kw: object) -> None:
        send_calls.append((content, message_type))

    with (
        patch.object(bob_agent, "process", mock_process),
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message", side_effect=capture_send),
    ):
        await bob_agent.handle_reject("Fix P2", {"page_id": "2"})

    # Index was updated to page 2
    assert bob_agent.current_page_index == 1

    # Ack sent BEFORE PROCESSING transition
    ack_idx = next(i for i, (c, _) in enumerate(send_calls) if "reprocessing" in c.lower())
    assert ack_idx == 0  # first send was the ack

    # Updated page stored
    assert bob_agent.pages[1]["requirement_md"] == "# P2 Revised"

    # Verify final state (the re-emitted is_review_ready payload is asserted by the
    # dedicated test test_bob_handle_reject_re_emits_is_review_ready_metadata below).
    final_state_call = mock_transition.call_args_list[-1]
    assert str(AgentState.REVIEW_REQUEST) in str(final_state_call)


@pytest.mark.asyncio
async def test_bob_handle_reject_re_emits_is_review_ready_metadata(bob_agent: BobAgent) -> None:
    """handle_reject re-emits is_review_ready=True in final send_message metadata."""
    bob_agent.pages = [
        {
            "page_id": "1",
            "page_title": "P1",
            "source_url": "https://example.com/p1",
            "raw_html": "<p>x</p>",
            "requirement_md": "# P1",
            "quality_issues": [],
        }
    ]
    bob_agent.current_page_index = 0
    updated = {**bob_agent.pages[0], "requirement_md": "# Revised"}
    mock_process = AsyncMock(
        return_value=StageResult(success=True, data=updated, errors=[], warnings=[], confidence=1.0)
    )

    metadata_sent: list[dict] = []

    async def capture_send(
        content: str, message_type: str = "text", metadata: dict | None = None, **_kw: object
    ) -> None:
        if metadata:
            metadata_sent.append(metadata)

    with (
        patch.object(bob_agent, "process", mock_process),
        patch.object(bob_agent, "transition_to"),
        patch.object(bob_agent, "send_message", side_effect=capture_send),
    ):
        await bob_agent.handle_reject("Fix it", {"page_id": "1"})

    is_review = [m for m in metadata_sent if m.get("is_review_ready")]
    assert len(is_review) == 1
    assert is_review[0]["pages"] == bob_agent.pages


@pytest.mark.asyncio
async def test_bob_handle_reject_defaults_to_current_when_no_page_id(bob_agent: BobAgent) -> None:
    """handle_reject with no page_id uses the existing current_page_index."""
    bob_agent.pages = [
        {
            "page_id": "1",
            "page_title": "P1",
            "source_url": "https://example.com/p1",
            "raw_html": "<p>x</p>",
            "requirement_md": "# P1",
            "quality_issues": [],
        }
    ]
    bob_agent.current_page_index = 0
    updated = {**bob_agent.pages[0], "requirement_md": "# Updated"}
    mock_process = AsyncMock(
        return_value=StageResult(success=True, data=updated, errors=[], warnings=[], confidence=1.0)
    )

    with (
        patch.object(bob_agent, "process", mock_process),
        patch.object(bob_agent, "transition_to"),
        patch.object(bob_agent, "send_message"),
    ):
        await bob_agent.handle_reject("feedback", None)

    assert bob_agent.pages[0]["requirement_md"] == "# Updated"
    assert bob_agent.current_page_index == 0  # unchanged


@pytest.mark.asyncio
async def test_bob_process_disconnects_mcp_on_completion(bob_agent: BobAgent) -> None:
    """AC3: process() must call disconnect() on the MCP client to release server session."""
    input_data = {
        "confluence_url": "https://company.atlassian.net/wiki/spaces/TEST/pages/111/Test",
    }

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        await bob_agent.process(input_data)

        # disconnect must be called to release MCP session
        mock_client.disconnect.assert_called()


@pytest.mark.asyncio
async def test_bob_extract_descendants_disconnects_mcp_on_exception(bob_agent: BobAgent) -> None:
    """AC3: _extract_descendants() must call disconnect() even if an exception occurs."""
    bob_agent._page_id = "12345"

    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter"),
        patch("ai_qa.agents.bob.ContentParser"),
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.side_effect = Exception("Simulated error")
        mock_reader.read_page_by_id.return_value = StageResult(
            success=False, data=None, errors=["mock failure"], warnings=[], confidence=0.0
        )
        mock_reader_class.return_value = mock_reader

        with pytest.raises(Exception, match="Simulated error"):
            await bob_agent._extract_descendants("Test Parent")

        mock_client.disconnect.assert_called_once()


@pytest.mark.asyncio
async def test_bob_extract_descendants_disconnects_mcp_on_completion(bob_agent: BobAgent) -> None:
    """AC3: _extract_descendants() must call disconnect() when done, releasing the MCP session."""
    bob_agent._page_id = "12345"

    # Configure project mock to return a Project-like object with confluence_base_url
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter"),
        patch("ai_qa.agents.bob.ContentParser"),
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config") as mock_llm_config,
    ):
        mock_llm_config.return_value = MagicMock()
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=False, data=None, errors=["mock failure"], warnings=[], confidence=0.0
        )
        mock_reader_class.return_value = mock_reader

        await bob_agent._extract_descendants("Test Parent")

        # The MCP client MUST be disconnected via except/finally handler
        mock_client.disconnect.assert_called()


@pytest.mark.asyncio
async def test_bob_get_llm_config_raises_on_missing_api_key(
    bob_agent: BobAgent,
) -> None:
    """Patch 7: get_llm_config() raises PipelineError with UX-DR12 format when API key is missing."""
    # Ensure project_context exists so the production path is taken
    assert bob_agent.project_context is not None

    # Mock the secret service to return None (no secret stored)
    with (
        patch("ai_qa.secrets.service.get_user_secret", return_value=None),
        patch.dict("os.environ", {}, clear=True),
    ):
        with pytest.raises(PipelineError, match="API key not configured"):
            bob_agent.get_llm_config()


@pytest.mark.asyncio
async def test_bob_process_raises_on_missing_mcp_secret(
    bob_agent: BobAgent,
) -> None:
    """Patch 10: process() raises PipelineError when get_user_secret returns None."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with patch("ai_qa.agents.bob.get_user_secret", return_value=None):
        with pytest.raises(PipelineError, match="MCP PAT not configured"):
            await bob_agent.process(input_data)


@pytest.mark.asyncio
async def test_bob_extract_descendants_raises_on_missing_mcp_secret(
    bob_agent: BobAgent,
) -> None:
    """Patch 10: _extract_descendants() raises PipelineError when get_user_secret returns None."""
    bob_agent._page_id = "12345"
    bob_agent._space_key = "TEST"

    with patch("ai_qa.agents.bob.get_user_secret", return_value=None):
        with pytest.raises(PipelineError, match="MCP PAT not configured"):
            await bob_agent._extract_descendants("Test Parent")


@pytest.mark.asyncio
async def test_bob_process_raises_on_empty_string_mcp_secret(
    bob_agent: BobAgent,
) -> None:
    """Patch 9: process() raises PipelineError when secret is empty string."""
    input_data = {"confluence_url": "https://company.atlassian.net/wiki/spaces/TEST"}

    with patch("ai_qa.agents.bob.get_user_secret", return_value=""):
        with pytest.raises(PipelineError, match="MCP PAT not configured"):
            await bob_agent.process(input_data)


# ---------------------------------------------------------------------------
# Story 11.2 — Intake gate tests
# ---------------------------------------------------------------------------

_VALID_CONF_URL = "https://company.atlassian.net/wiki/spaces/TEST/pages/12345/Title"
_CONFIGURED_MCP = SecretStatus(
    secret_type="mcp",
    configured=True,
    status="configured",
    last_updated=None,
    validation_state="configured",
)
_UNCONFIGURED_MCP = SecretStatus(
    secret_type="mcp",
    configured=False,
    status="missing",
    last_updated=None,
    validation_state="missing",
)


# --- AC3: precondition checks ---


@pytest.mark.asyncio
async def test_bob_gate_blocks_when_thread_context_missing(bob_agent: BobAgent) -> None:
    """AC3: missing thread_id → blocking message sent, no MCP connection."""
    bob_agent.project_context.thread_id = None  # type: ignore[attr-defined]

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
        mock_mcp.assert_not_called()
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs.get("message_type") == "error"


@pytest.mark.asyncio
async def test_bob_gate_blocks_when_thread_missing_provider_name(
    bob_agent: BobAgent,
) -> None:
    """AC3: thread with no provider_name → blocking message, no MCP."""
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    # Thread has no provider_name
    mock_thread = MagicMock()
    mock_thread.provider_name = None
    mock_thread.agent_configs = {"bob": {"model": "claude-sonnet"}}
    bob_agent.project_context.artifact_service.db.get.return_value = mock_thread

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
        assert mock_mcp.call_count == 0
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs.get("message_type") == "error"
        assert "Alice" in mock_send.call_args[0][0]


@pytest.mark.asyncio
async def test_bob_gate_blocks_when_bob_model_missing(bob_agent: BobAgent) -> None:
    """AC3: thread has provider_name but no bob model config → blocking message, no MCP."""
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_thread = MagicMock()
    mock_thread.provider_name = "claude"
    mock_thread.agent_configs = {}  # no "bob" entry
    bob_agent.project_context.artifact_service.db.get.return_value = mock_thread

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
        assert mock_mcp.call_count == 0
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs.get("message_type") == "error"


@pytest.mark.asyncio
async def test_bob_gate_blocks_when_mcp_not_configured(bob_agent: BobAgent) -> None:
    """AC3: MCP credential not configured → blocking message, MCPClient never instantiated."""
    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch("ai_qa.agents.bob.get_secret_status", return_value=_UNCONFIGURED_MCP),
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
        assert mock_mcp.call_count == 0
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs.get("message_type") == "error"
        assert "MCP key" in mock_send.call_args[0][0]


# --- AC2: _validate_confluence_url unit tests ---


def test_validate_confluence_url_empty_returns_none(bob_agent: BobAgent) -> None:
    assert bob_agent._validate_confluence_url("", None) is None
    assert bob_agent._validate_confluence_url("   ", None) is None


def test_validate_confluence_url_invalid_format_returns_hint(bob_agent: BobAgent) -> None:
    result = bob_agent._validate_confluence_url("not-a-url", None)
    assert result is not None
    assert "Expected formats" in result


def test_validate_confluence_url_wrong_host_vs_configured_base(bob_agent: BobAgent) -> None:
    url = "https://evil.com/wiki/spaces/HACK/pages/111/Title"
    base = "https://company.atlassian.net"
    result = bob_agent._validate_confluence_url(url, base)
    assert result is not None
    assert "company.atlassian.net" in result


def test_validate_confluence_url_valid_cloud_matching_host_returns_none(
    bob_agent: BobAgent,
) -> None:
    url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123/Title"
    base = "https://company.atlassian.net/wiki"
    assert bob_agent._validate_confluence_url(url, base) is None


def test_validate_confluence_url_valid_no_base_configured_returns_none(bob_agent: BobAgent) -> None:
    url = "https://company.atlassian.net/wiki/spaces/TEST/pages/123/Title"
    assert bob_agent._validate_confluence_url(url, None) is None


@pytest.mark.asyncio
async def test_bob_gate_invalid_url_blocks_before_mcp(bob_agent: BobAgent) -> None:
    """AC2: invalid confluence_url → correction sent, MCPClient not instantiated."""
    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
        patch.object(bob_agent, "send_message") as mock_send,
    ):
        await bob_agent.handle_start({"confluence_url": "not-a-url"})
        assert mock_mcp.call_count == 0
        assert mock_send.call_count == 2
        _, kwargs = mock_send.call_args_list[-1]
        assert kwargs.get("message_type") == "error"


# --- AC1: _validate_jira_ref unit tests ---


def test_validate_jira_ref_jira_disabled_ignores_any_input(bob_agent: BobAgent) -> None:
    assert bob_agent._validate_jira_ref("PROJ-123", None) is None
    assert bob_agent._validate_jira_ref("https://jira.company.com/x", None) is None
    assert bob_agent._validate_jira_ref("garbage", None) is None


def test_validate_jira_ref_jira_enabled_empty_ref_returns_none(bob_agent: BobAgent) -> None:
    assert bob_agent._validate_jira_ref(None, "https://jira.company.com") is None
    assert bob_agent._validate_jira_ref("", "https://jira.company.com") is None
    assert bob_agent._validate_jira_ref("   ", "https://jira.company.com") is None


def test_validate_jira_ref_valid_bare_key_returns_none(bob_agent: BobAgent) -> None:
    assert bob_agent._validate_jira_ref("PROJ-123", "https://jira.company.com") is None
    assert bob_agent._validate_jira_ref("AB-1", "https://jira.company.com") is None


def test_validate_jira_ref_valid_same_host_url_returns_none(bob_agent: BobAgent) -> None:
    assert (
        bob_agent._validate_jira_ref(
            "https://jira.company.com/browse/PROJ-1", "https://jira.company.com"
        )
        is None
    )


def test_validate_jira_ref_foreign_host_url_returns_correction(bob_agent: BobAgent) -> None:
    result = bob_agent._validate_jira_ref(
        "https://evil.atlassian.net/browse/PROJ-1", "https://jira.company.com"
    )
    assert result is not None
    assert "jira.company.com" in result


def test_validate_jira_ref_garbage_returns_correction(bob_agent: BobAgent) -> None:
    result = bob_agent._validate_jira_ref("not-a-ticket", "https://jira.company.com")
    assert result is not None


@pytest.mark.asyncio
async def test_bob_gate_stashes_valid_jira_ref(bob_agent: BobAgent) -> None:
    """AC1: valid Jira ref is stashed on self._jira_ref after gate passes."""
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = None
    mock_project.jira_base_url = "https://jira.company.com"
    mock_thread = MagicMock()
    mock_thread.provider_name = "claude"
    mock_thread.agent_configs = {"bob": {"model": "claude-sonnet"}}

    def side_effect(model: type, ident: object, **kw: object) -> object:
        from ai_qa.db.models import Project
        from ai_qa.threads.models import Thread

        if model is Thread:
            return mock_thread
        if model is Project:
            return mock_project
        return MagicMock()

    bob_agent.project_context.artifact_service.db.get.side_effect = side_effect

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
        patch.object(bob_agent, "process", new_callable=AsyncMock) as mock_proc,
    ):
        mock_mcp_instance = AsyncMock()
        mock_mcp.return_value = mock_mcp_instance
        mock_proc.return_value = StageResult(
            success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
        )
        await bob_agent.handle_start(
            {
                "confluence_url": _VALID_CONF_URL,
                "jira_url": "PROJ-99",
            }
        )
        assert bob_agent._jira_ref == "PROJ-99"


@pytest.mark.asyncio
@patch("ai_qa.agents.bob.MCPClient")
@patch("ai_qa.agents.bob.ConfluenceReader")
async def test_bob_gate_happy_path_reaches_confirm_parent(
    mock_reader_class: MagicMock, mock_mcp_client_class: MagicMock, bob_agent: BobAgent
) -> None:
    """Happy-path regression: valid start with all preconditions met reaches confirm_parent."""
    mock_reader_class.return_value.check_tool_availability = AsyncMock(return_value=[])
    mock_mcp_client_class.return_value.connect = AsyncMock()
    mock_mcp_client_class.return_value.disconnect = AsyncMock()
    with (
        patch("ai_qa.agents.bob.get_secret_status", return_value=_CONFIGURED_MCP),
        patch.object(bob_agent, "process", new_callable=AsyncMock) as mock_proc,
    ):
        mock_proc.return_value = StageResult(
            success=True, data={"type": "confirm_parent", "suggested_page": "url1"}
        )
        await bob_agent.handle_start({"confluence_url": _VALID_CONF_URL})
        assert bob_agent.phase == "confirm_parent"
        assert bob_agent.state == AgentState.REVIEW_REQUEST
        mock_proc.assert_called_once()


# ---------------------------------------------------------------------------
# Story 11.3 — ContentParser wiring (AC2/AC3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bob_extract_descendants_wires_content_parser(bob_agent: BobAgent) -> None:
    """AC2/AC3: ContentParser.parse() is called; clean markdown and warnings carried forward."""
    from datetime import UTC, datetime

    from ai_qa.pipelines.models import ConfluencePage, ParsedContent

    # Use page_id matching mock_page so summaries has exactly one entry
    bob_agent._page_id = "page-1"
    bob_agent._space_key = "TEST"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    mock_page = ConfluencePage(
        page_id="page-1",
        title="My Page",
        content="<p>Hello</p>",
        space_key="TEST",
        url="https://confluence.company.com/page-1",
        retrieved_at=datetime.now(UTC),
        labels=[],
    )
    clean_md = "# Clean\n| a | b |\n| --- | --- |\n| 1 | 2 |"
    gliffy_warning = "Gliffy diagram detected — manual review recommended"
    parsed_content = ParsedContent(
        page_id="page-1",
        page_title="My Page",
        source_url="https://confluence.company.com/page-1",
        markdown=clean_md,
        mermaid_diagrams=[],
        image_paths=[],
        test_cases_detected=[],
        parsed_at=datetime.now(UTC),
    )
    parse_result = StageResult(
        success=True,
        data=parsed_content,
        errors=[],
        warnings=[gliffy_warning],
        confidence=0.8,
    )

    mock_formatter = AsyncMock()
    mock_formatter.convert_markdown.return_value = "# Story"
    mock_parser = AsyncMock()
    mock_parser.parse.return_value = parse_result
    mock_adapter = MagicMock()

    with (
        patch("ai_qa.agents.bob.MCPClient", return_value=AsyncMock()),
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter", return_value=mock_adapter),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_reader = AsyncMock()
        # Return no children — the parent page (page-1) is added to summaries automatically
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True,
            data=[],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=mock_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants("My Page")

    assert result.success
    assert len(bob_agent.pages) == 1
    page = bob_agent.pages[0]

    # AC2: clean markdown carried forward on the page dict
    assert page["parsed_markdown"] == clean_md
    assert page["requirement_md"] == "# Story"

    # AC3: Gliffy warning surfaced, not dropped
    assert gliffy_warning in page["warnings"]

    # convert_markdown was called with the page + clean_md (auth_token passed as a
    # kwarg for the image fetch); convert_page must NOT have been called.
    mock_formatter.convert_markdown.assert_called_once()
    assert mock_formatter.convert_markdown.call_args.args == (mock_page, clean_md)
    mock_formatter.convert_page.assert_not_called()


@pytest.mark.asyncio
async def test_bob_extract_descendants_reuses_unchanged_pages(bob_agent: BobAgent) -> None:
    """Change-detection reuse: saved pages whose Confluence version is unchanged are
    reused — convert_markdown is NOT called and saved content is carried forward. The
    child's version comes from the listing (no per-child fetch); only the parent is
    fetched once to resolve its real title + version."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from ai_qa.pipelines.models import ConfluencePage, PageSummary

    bob_agent._page_id = "parent-1"
    bob_agent._space_key = "TEST"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    parent_page = ConfluencePage(
        page_id="parent-1",
        title="Parent Page",
        content="<p>P</p>",
        space_key="TEST",
        url="https://confluence.company.com/parent-1",
        retrieved_at=datetime.now(UTC),
        labels=[],
        version=3,
    )

    mock_formatter = AsyncMock()
    mock_parser = AsyncMock()
    mock_adapter = MagicMock()
    # Parent (v3) and child (v7) are both already saved at their current versions.
    mock_adapter.load_requirement_markdown.return_value = [
        SimpleNamespace(name="parent-1.md", content="# Parent saved"),
        SimpleNamespace(name="child-1.md", content="# Child saved"),
    ]
    mock_adapter.load_all_metadata.return_value = {
        "parent-1/requirement.metadata.json": {"source_version": 3},
        "child-1/requirement.metadata.json": {"source_version": 7},
    }

    with (
        patch("ai_qa.agents.bob.MCPClient", return_value=AsyncMock()),
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter", return_value=mock_adapter),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True,
            data=[
                PageSummary(
                    page_id="child-1",
                    title="Child",
                    url="https://confluence.company.com/child-1",
                    version=7,
                )
            ],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=parent_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants("https://confluence.company.com/parent-1")

    assert result.success
    pages = {p["page_id"]: p for p in bob_agent.pages}
    assert pages["parent-1"]["requirement_md"] == "# Parent saved"
    assert pages["child-1"]["requirement_md"] == "# Child saved"
    # No LLM conversion for either unchanged page.
    mock_formatter.convert_markdown.assert_not_called()
    # Child reused via the listing version (no fetch); parent fetched exactly once.
    mock_reader.read_page_by_id.assert_called_once_with("parent-1")


@pytest.mark.asyncio
async def test_bob_extract_descendants_reuse_prefers_approved_over_draft(
    bob_agent: BobAgent,
) -> None:
    """When both a draft ('{pid}.md') and an approved ('{pid}/requirement.md') copy
    exist, the approved (post-clarify) content is reused — even if the draft is listed
    first — never the stale draft."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from ai_qa.pipelines.models import ConfluencePage

    bob_agent._page_id = "page-1"
    bob_agent._space_key = "TEST"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    mock_page = ConfluencePage(
        page_id="page-1",
        title="My Page",
        content="<p>Hello</p>",
        space_key="TEST",
        url="https://confluence.company.com/page-1",
        retrieved_at=datetime.now(UTC),
        labels=[],
        version=7,
    )

    mock_formatter = AsyncMock()
    mock_parser = AsyncMock()
    mock_adapter = MagicMock()
    # Draft listed FIRST (the worst case for precedence); approved must still win.
    # Both copies are at the current version (7) → unchanged → reused.
    mock_adapter.load_requirement_markdown.return_value = [
        SimpleNamespace(name="page-1.md", content="# DRAFT stale"),
        SimpleNamespace(name="page-1/requirement.md", content="# APPROVED final"),
    ]
    mock_adapter.load_all_metadata.return_value = {
        "page-1/requirement.metadata.json": {"source_version": 7}
    }

    with (
        patch("ai_qa.agents.bob.MCPClient", return_value=AsyncMock()),
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter", return_value=mock_adapter),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=mock_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants("My Page")

    assert result.success
    assert len(bob_agent.pages) == 1
    assert bob_agent.pages[0]["requirement_md"] == "# APPROVED final"
    mock_formatter.convert_markdown.assert_not_called()


@pytest.mark.asyncio
async def test_bob_extract_descendants_reextracts_on_version_change(bob_agent: BobAgent) -> None:
    """When the Confluence version changed since the saved copy, the page is re-extracted
    (convert_markdown IS called), the stale requirement is overridden, and the new version
    is persisted to the per-page sidecar."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from ai_qa.pipelines.models import ConfluencePage, ParsedContent

    bob_agent._page_id = "page-1"
    bob_agent._space_key = "TEST"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    # Saved at v3; Confluence now reports v5 → changed → must re-extract.
    page_v5 = ConfluencePage(
        page_id="page-1",
        title="My Page",
        content="<p>New content</p>",
        space_key="TEST",
        url="https://confluence.company.com/page-1",
        retrieved_at=datetime.now(UTC),
        labels=[],
        version=5,
    )
    parse_result = StageResult(
        success=True,
        data=ParsedContent(
            page_id="page-1",
            page_title="My Page",
            source_url="https://confluence.company.com/page-1",
            markdown="# Clean new content with enough length",
            mermaid_diagrams=[],
            image_paths=[],
            test_cases_detected=[],
            parsed_at=datetime.now(UTC),
        ),
        errors=[],
        warnings=[],
        confidence=0.9,
    )

    mock_formatter = AsyncMock()
    mock_formatter.convert_markdown.return_value = "# Re-extracted"
    mock_parser = AsyncMock()
    mock_parser.parse.return_value = parse_result
    mock_adapter = MagicMock()
    mock_adapter.load_requirement_markdown.return_value = [
        SimpleNamespace(name="page-1.md", content="# STALE saved")
    ]
    mock_adapter.load_all_metadata.return_value = {
        "page-1/requirement.metadata.json": {"source_version": 3}
    }

    with (
        patch("ai_qa.agents.bob.MCPClient", return_value=AsyncMock()),
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter", return_value=mock_adapter),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=page_v5, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants("https://confluence.company.com/page-1")

    assert result.success
    assert len(bob_agent.pages) == 1
    page = bob_agent.pages[0]
    # Overridden with the freshly converted content (NOT the stale saved copy).
    assert page["requirement_md"] == "# Re-extracted"
    assert page["source_version"] == 5
    mock_formatter.convert_markdown.assert_called_once()
    # The new version was persisted to the per-page sidecar at convert time.
    persisted = [c.args[1].get("source_version") for c in mock_adapter.save_metadata.call_args_list]
    assert 5 in persisted


@pytest.mark.asyncio
async def test_bob_extract_descendants_parent_node_uses_real_title(bob_agent: BobAgent) -> None:
    """Regression: the prepended parent node must show its real Confluence title, not the
    URL the user confirmed — including on the reuse path (where the bug lived)."""
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from ai_qa.pipelines.models import ConfluencePage

    bob_agent._page_id = "777945456"
    bob_agent._space_key = "CORPHRSOL"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.svc.corp.ch"
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    confirmed_url = (
        "https://confluence.svc.corp.ch/spaces/CORPHRSOL/pages/777945456/General+knowledge"
    )
    parent_page = ConfluencePage(
        page_id="777945456",
        title="General knowledge",
        content="<p>Body</p>",
        space_key="CORPHRSOL",
        url=confirmed_url,
        retrieved_at=datetime.now(UTC),
        labels=[],
        version=2,
    )

    mock_formatter = AsyncMock()
    mock_parser = AsyncMock()
    mock_adapter = MagicMock()
    # Parent saved at the current version (2) → reused (the path that showed the URL).
    mock_adapter.load_requirement_markdown.return_value = [
        SimpleNamespace(name="777945456.md", content="# Saved")
    ]
    mock_adapter.load_all_metadata.return_value = {
        "777945456/requirement.metadata.json": {"source_version": 2}
    }

    with (
        patch("ai_qa.agents.bob.MCPClient", return_value=AsyncMock()),
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter", return_value=mock_adapter),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=parent_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants(confirmed_url)

    assert result.success
    assert len(bob_agent.pages) == 1
    # The node title is the real page title, NOT the confirmed URL.
    assert bob_agent.pages[0]["page_title"] == "General knowledge"
    assert bob_agent.pages[0]["page_title"] != confirmed_url
    mock_formatter.convert_markdown.assert_not_called()


@pytest.mark.asyncio
async def test_bob_extract_descendants_no_silent_drop_on_parse_failure(bob_agent: BobAgent) -> None:
    """AC3: page with ContentParser.parse() data=None still appears in self.pages with warnings."""
    from datetime import UTC, datetime

    from ai_qa.pipelines.models import ConfluencePage

    # page_id matches mock_page so summaries has exactly one entry (no children)
    bob_agent._page_id = "page-1"
    bob_agent._space_key = "TEST"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    bob_agent.project_context.artifact_service.db.get.return_value = MagicMock(
        confluence_base_url=None
    )

    mock_page = ConfluencePage(
        page_id="page-1",
        title="Bad Page",
        content="<p>Content</p>",
        space_key="TEST",
        url="https://confluence.company.com/page-1",
        retrieved_at=datetime.now(UTC),
        labels=[],
    )
    failed_parse = StageResult(
        success=False,
        data=None,
        errors=["Parse error"],
        warnings=["HTML-to-Markdown conversion failed — content unavailable: timeout"],
        confidence=0.0,
    )

    mock_formatter = AsyncMock()
    mock_formatter.convert_markdown.return_value = "# Fallback Story"
    mock_parser = AsyncMock()
    mock_parser.parse.return_value = failed_parse
    mock_adapter = MagicMock()

    with (
        patch("ai_qa.agents.bob.MCPClient", return_value=AsyncMock()),
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter", return_value=mock_adapter),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_reader = AsyncMock()
        # No children — only the parent page (page-1) in summaries
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True,
            data=[],
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=mock_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants("Bad Page")

    # Page must be in self.pages even when parse() returned data=None (AC3: warn, not drop)
    assert len(bob_agent.pages) == 1
    page = bob_agent.pages[0]
    assert page["page_id"] == "page-1"
    assert any("HTML-to-Markdown conversion failed" in w for w in page["warnings"])
    # run must not crash and reports success (fallback clean_md was used)
    assert result.success


# ---------------------------------------------------------------------------
# Story 11.4 — Jira requirements retrieval (AC1/AC2/AC3)
# ---------------------------------------------------------------------------


def _make_jira_issue(**kwargs: object) -> JiraIssue:
    """Factory for test JiraIssue instances with sensible defaults."""
    defaults: dict[str, object] = {
        "issue_key": "PROJ-123",
        "summary": "Login fails on SSO",
        "description": "Steps to reproduce...",
        "acceptance_criteria": "Given SSO configured Then login succeeds",
        "status": "In Progress",
        "labels": ["auth", "regression"],
        "project_key": "PROJ",
        "url": "https://jira.company.com/browse/PROJ-123",
        "retrieved_at": datetime.now(UTC),
        "issue_type": "Story",
        "reporter": None,
        "assignee": None,
    }
    defaults.update(kwargs)
    return JiraIssue(**defaults)  # type: ignore[arg-type]


# --- 5.2: _format_jira_markdown (AC2, pure sync) ---


def test_format_jira_markdown_full_issue(bob_agent: BobAgent) -> None:
    """Fully-populated issue renders all expected fields; labels joined, not raw list."""
    issue = _make_jira_issue()
    result = bob_agent._format_jira_markdown(issue)

    assert "PROJ-123" in result
    assert "Login fails on SSO" in result
    assert "In Progress" in result
    assert "Story" in result
    assert "auth, regression" in result
    assert "## Description" in result
    assert "Steps to reproduce" in result
    assert "## Acceptance Criteria" in result
    assert "Given SSO configured" in result
    assert "https://jira.company.com/browse/PROJ-123" in result
    # Raw list form must never appear
    assert "['auth'" not in result
    assert "['regression'" not in result


def test_format_jira_markdown_minimal_issue(bob_agent: BobAgent) -> None:
    """Minimal issue (no description/AC/labels/status) has no None leakage or empty sections."""
    issue = _make_jira_issue(
        description=None,
        acceptance_criteria=None,
        labels=[],
        status=None,
        issue_type=None,
    )
    result = bob_agent._format_jira_markdown(issue)

    assert "None" not in result
    assert "## Description" not in result
    assert "## Acceptance Criteria" not in result
    assert "**Labels:**" not in result
    assert "**Status:**" not in result
    # Issue key and summary still present
    assert "PROJ-123" in result
    assert "Login fails on SSO" in result


# --- 5.3: AC1 — tools unavailable skips retrieval ---


@pytest.mark.asyncio
async def test_retrieve_jira_tools_unavailable_skips(bob_agent: BobAgent) -> None:
    """AC1: when check_tool_availability returns missing tools, read_issue is never called."""
    bob_agent._jira_ref = "PROJ-123"
    mock_client = MagicMock()

    with patch("ai_qa.agents.bob.JiraReader") as mock_jira_reader_class:
        mock_reader = MagicMock()
        mock_reader.check_tool_availability = AsyncMock(return_value=["jira_get_issue"])
        mock_reader.read_issue = AsyncMock()
        mock_jira_reader_class.return_value = mock_reader

        warnings = await bob_agent._retrieve_jira_requirements(
            mock_client, "https://jira.company.com"
        )

    mock_reader.read_issue.assert_not_awaited()
    assert not any(p.get("source_type") == "jira" for p in bob_agent.pages)
    assert len(warnings) > 0
    assert any("unavailable" in w.lower() or "skip" in w.lower() for w in warnings)


# --- 5.4: AC2 — happy path appends rich review item ---


@pytest.mark.asyncio
async def test_retrieve_jira_happy_path_appends_item(bob_agent: BobAgent) -> None:
    """AC2: successful retrieval appends a Jira review item to self.pages."""
    bob_agent._jira_ref = "PROJ-123"
    issue = _make_jira_issue()
    mock_client = MagicMock()

    with patch("ai_qa.agents.bob.JiraReader") as mock_jira_reader_class:
        mock_reader = MagicMock()
        mock_reader.check_tool_availability = AsyncMock(return_value=[])
        mock_reader.read_issue = AsyncMock(
            return_value=StageResult(
                success=True, data=issue, errors=[], warnings=[], confidence=1.0
            )
        )
        mock_jira_reader_class.return_value = mock_reader

        warnings = await bob_agent._retrieve_jira_requirements(
            mock_client, "https://jira.company.com"
        )

    assert warnings == []
    assert len(bob_agent.pages) == 1
    item = bob_agent.pages[-1]
    assert item["source_type"] == "jira"
    assert item["page_id"] == "PROJ-123"
    assert item["page_title"].startswith("[PROJ-123]")
    assert item["source_url"] == "https://jira.company.com/browse/PROJ-123"
    assert "Steps to reproduce" in item["requirement_md"]
    assert "Given SSO configured" in item["requirement_md"]


# --- 5.5: AC3 — soft retrieval failure does not crash ---


@pytest.mark.asyncio
async def test_retrieve_jira_soft_failure_returns_warning(bob_agent: BobAgent) -> None:
    """AC3: read_issue soft-fail → warning returned, no item appended, no exception."""
    bob_agent._jira_ref = "PROJ-123"
    mock_client = MagicMock()

    with patch("ai_qa.agents.bob.JiraReader") as mock_jira_reader_class:
        mock_reader = MagicMock()
        mock_reader.check_tool_availability = AsyncMock(return_value=[])
        mock_reader.read_issue = AsyncMock(
            return_value=StageResult(
                success=False, data=None, errors=["Jira tool error"], warnings=[], confidence=0.0
            )
        )
        mock_jira_reader_class.return_value = mock_reader

        warnings = await bob_agent._retrieve_jira_requirements(
            mock_client, "https://jira.company.com"
        )

    assert not any(p.get("source_type") == "jira" for p in bob_agent.pages)
    assert len(warnings) > 0


# --- 5.6: AC3 — exception safety ---


@pytest.mark.asyncio
async def test_retrieve_jira_exception_returns_warning_not_raise(bob_agent: BobAgent) -> None:
    """AC3: exception from check_tool_availability is caught; returns warning, does not raise."""
    bob_agent._jira_ref = "PROJ-123"
    initial_pages = list(bob_agent.pages)
    mock_client = MagicMock()

    with patch("ai_qa.agents.bob.JiraReader") as mock_jira_reader_class:
        mock_reader = MagicMock()
        mock_reader.check_tool_availability = AsyncMock(side_effect=MCPConnectionError("down"))
        mock_jira_reader_class.return_value = mock_reader

        warnings = await bob_agent._retrieve_jira_requirements(
            mock_client, "https://jira.company.com"
        )

    assert len(warnings) > 0
    assert bob_agent.pages == initial_pages


# --- 5.7: No-ref short-circuit ---


@pytest.mark.asyncio
async def test_retrieve_jira_no_ref_returns_empty_no_reader(bob_agent: BobAgent) -> None:
    """When _jira_ref is None, JiraReader is never constructed and [] is returned."""
    bob_agent._jira_ref = None
    mock_client = MagicMock()

    with patch("ai_qa.agents.bob.JiraReader") as mock_jira_reader_class:
        warnings = await bob_agent._retrieve_jira_requirements(
            mock_client, "https://jira.company.com"
        )
        mock_jira_reader_class.assert_not_called()

    assert warnings == []


# --- 5.8: Integration in _extract_descendants (AC2 end-to-end) ---


@pytest.mark.asyncio
async def test_bob_extract_descendants_with_jira_produces_two_pages(bob_agent: BobAgent) -> None:
    """AC2 integration: _extract_descendants yields 1 Confluence + 1 Jira page when Jira ref set."""
    bob_agent._page_id = "12345"
    bob_agent._jira_ref = "PROJ-123"

    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    mock_project.jira_base_url = "https://jira.company.com"
    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    mock_confluence_page = MagicMock()
    mock_confluence_page.page_id = "12345"
    mock_confluence_page.title = "Parent"
    mock_confluence_page.content = "<p>x</p>"
    mock_confluence_page.url = "https://confluence.company.com/x"

    jira_issue = _make_jira_issue()

    mock_client = AsyncMock()
    mock_client.is_connected = True

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter") as mock_formatter_class,
        patch("ai_qa.agents.bob.ContentParser") as mock_parser_class,
        patch("ai_qa.agents.bob.PipelineArtifactAdapter"),
        patch("ai_qa.agents.bob.JiraReader") as mock_jira_reader_class,
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.check_tool_availability = AsyncMock(return_value=[])
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=mock_confluence_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        mock_formatter_class.return_value.convert_markdown = AsyncMock(return_value="# Req")

        mock_parser_inst = AsyncMock()
        mock_parser_inst.parse.return_value = StageResult(
            success=True,
            data=MagicMock(markdown="# Clean"),
            errors=[],
            warnings=[],
            confidence=1.0,
        )
        mock_parser_class.return_value = mock_parser_inst

        mock_jira_reader = MagicMock()
        mock_jira_reader.check_tool_availability = AsyncMock(return_value=[])
        mock_jira_reader.read_issue = AsyncMock(
            return_value=StageResult(
                success=True, data=jira_issue, errors=[], warnings=[], confidence=1.0
            )
        )
        mock_jira_reader_class.return_value = mock_jira_reader

        result = await bob_agent._extract_descendants("Parent")

    assert result.success is True
    assert len(bob_agent.pages) == 2

    jira_pages = [p for p in bob_agent.pages if p.get("source_type") == "jira"]
    confluence_pages = [p for p in bob_agent.pages if p.get("source_type") != "jira"]
    assert len(jira_pages) == 1
    assert len(confluence_pages) == 1
    assert jira_pages[0]["page_id"] == "PROJ-123"
    assert result.warnings == []

    # MCPClient still instantiated only once
    assert mock_mcp_client_class.call_count == 1


# ---------------------------------------------------------------------------
# Story 11.7 — Requirements Artifact Save (AC1/AC3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bob_handle_approve_saves_requirement_with_provenance(bob_agent: BobAgent) -> None:
    """Auto-save calls save_requirement with provenance from each page dict + side effects."""
    quality_issues = [
        {"category": "vague_language", "location": "P1", "message": "m", "impact": "i"}
    ]
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "P1",
            "source_url": "https://example.atlassian.net/p1",
            "source_type": "confluence",
            "requirement_md": "# P1",
            "quality_issues": quality_issues,
            "raw_html": "<p>x</p>",
        }
    ]

    with patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class:
        mock_adapter = mock_adapter_class.return_value
        mock_adapter.save_requirement.return_value = MagicMock()
        mock_adapter.save_metadata.return_value = MagicMock()

        saved = bob_agent._auto_save_requirements()

    assert saved == 1
    mock_adapter.save_requirement.assert_called_once()
    _, kwargs = mock_adapter.save_requirement.call_args
    assert kwargs["page_id"] == "p1"
    assert kwargs["markdown"] == "# P1"
    assert kwargs["source_type"] == "confluence"
    assert kwargs["source_url"] == "https://example.atlassian.net/p1"
    assert kwargs["warnings"] == quality_issues
    # The two companion side effects must also fire (else they could be silently dropped).
    mock_adapter.delete_draft_requirement.assert_called_once_with("p1")
    mock_adapter.save_metadata.assert_called_once()
    assert "p1" in bob_agent._resolved_page_ids


@pytest.mark.asyncio
async def test_bob_handle_approve_save_failure_keeps_page_reviewable(bob_agent: BobAgent) -> None:
    """Auto-save failure → error message, stays in confirm_parent (not select_id), no DONE."""
    bob_agent.phase = "confirm_parent"
    bob_agent.pages = []

    async def fake_extract(confirmed_page: str) -> StageResult:
        bob_agent.pages = [
            {
                "page_id": "p1",
                "page_title": "P1",
                "source_url": "https://example.atlassian.net/p1",
                "source_type": "confluence",
                "requirement_md": "# P1",
                "quality_issues": [],
            }
        ]
        return StageResult(
            success=True, data=bob_agent.pages, errors=[], warnings=[], confidence=1.0
        )

    send_message_calls: list[dict] = []

    async def capture_send(content: str, message_type: str = "text", **kw: object) -> None:
        send_message_calls.append({"content": content, "message_type": message_type})

    with (
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
        patch.object(bob_agent, "_extract_descendants", side_effect=fake_extract),
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message", side_effect=capture_send),
    ):
        mock_adapter = mock_adapter_class.return_value
        mock_adapter.save_requirement.side_effect = RuntimeError("storage down")

        await bob_agent.handle_approve(
            {"confirmed_page_name": "https://example.atlassian.net/wiki/spaces/T/pages/p1/P1"}
        )

    # Error message was sent asking to retry
    error_calls = [c for c in send_message_calls if c["message_type"] == "error"]
    assert len(error_calls) >= 1
    assert "retry" in error_calls[-1]["content"].lower()

    # Stayed in confirm_parent (did not advance to select_id) and never went DONE
    assert bob_agent.phase == "confirm_parent"
    assert all(AgentState.DONE not in c.args for c in mock_transition.call_args_list)


@pytest.mark.asyncio
async def test_bob_handle_approve_skip_no_saved_requirements_goes_done(
    bob_agent: BobAgent,
) -> None:
    """Blank link → action='skip' with NO saved requirements: bypass extraction and hand
    off to Mary (which then reports there is nothing to generate from)."""
    bob_agent.phase = "confirm_parent"

    send_message_calls: list[dict] = []

    async def capture_send(content: str, message_type: str = "text", **kw: object) -> None:
        send_message_calls.append({"content": content, "message_type": message_type})

    with (
        patch.object(bob_agent, "_extract_descendants") as mock_extract,
        patch.object(bob_agent, "_load_saved_requirement_pages", return_value=[]),
        patch.object(bob_agent, "transition_to") as mock_transition,
        patch.object(bob_agent, "send_message", side_effect=capture_send),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter"),
    ):
        await bob_agent.handle_approve({"action": "skip"})

    # Extraction was bypassed entirely.
    mock_extract.assert_not_called()
    # Went DONE so the pipeline advances to Mary.
    assert bob_agent.phase == "done"
    assert any(AgentState.DONE in c.args for c in mock_transition.call_args_list)
    assert any("handing" in c["content"].lower() for c in send_message_calls)


@pytest.mark.asyncio
async def test_bob_handle_approve_skip_with_saved_requirements_prompts_select_id(
    bob_agent: BobAgent,
) -> None:
    """Blank link → action='skip' WITH saved requirements: load them and prompt the user
    to pick ONE id (instead of jumping straight to Mary with all requirements)."""
    bob_agent.phase = "confirm_parent"

    saved_pages = [
        {
            "page_id": "12345",
            "page_title": "12345",
            "source_url": "https://confluence.example.com/12345",
            "source_type": "confluence",
            "requirement_md": "# Req\n\nSome content.",
        }
    ]
    send_message_calls: list[dict] = []

    async def capture_send(
        content: str = "", message_type: str = "text", metadata: dict | None = None, **kw: object
    ) -> None:
        send_message_calls.append(
            {"content": content, "message_type": message_type, "metadata": metadata}
        )

    with (
        patch.object(bob_agent, "_extract_descendants") as mock_extract,
        patch.object(bob_agent, "_load_saved_requirement_pages", return_value=saved_pages),
        patch.object(bob_agent, "transition_to"),
        patch.object(bob_agent, "send_message", side_effect=capture_send),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter"),
    ):
        await bob_agent.handle_approve({"action": "skip"})

    mock_extract.assert_not_called()
    # Routed to the id picker, NOT DONE.
    assert bob_agent.phase == "select_id"
    assert bob_agent.pages == saved_pages
    assert bob_agent.output_files_saved == 1
    assert any((c["metadata"] or {}).get("is_select_id") for c in send_message_calls)


@pytest.mark.asyncio
async def test_bob_handle_approve_unknown_phase_reports_reset(bob_agent: BobAgent) -> None:
    """An approve that matches no active phase (e.g. after a backend restart wiped the
    in-memory state) reports a recovery message instead of silently doing nothing."""
    bob_agent.phase = "init"

    send_message_calls: list[dict] = []

    async def capture_send(content: str = "", message_type: str = "text", **kw: object) -> None:
        send_message_calls.append({"content": content, "message_type": message_type})

    with patch.object(bob_agent, "send_message", side_effect=capture_send):
        await bob_agent.handle_approve({"action": "skip_file", "page_id": "p1"})

    assert len(send_message_calls) == 1
    assert send_message_calls[0]["message_type"] == "error"
    assert "restart" in send_message_calls[0]["content"].lower()


@pytest.mark.asyncio
async def test_bob_handle_approve_save_failure_no_mcp_client(bob_agent: BobAgent) -> None:
    """6.6 regression: save path opens NO MCP client — save failure does not touch MCPClient."""
    bob_agent.phase = "review_markdown"
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "P1",
            "source_url": "https://example.atlassian.net/p1",
            "source_type": "confluence",
            "requirement_md": "# P1",
            "quality_issues": [],
        }
    ]

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp,
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
        patch.object(bob_agent, "transition_to"),
        patch.object(bob_agent, "send_message"),
    ):
        mock_adapter_class.return_value.save_requirement.side_effect = RuntimeError("storage down")

        await bob_agent.handle_approve(
            {"action": "approved", "page_id": "p1", "markdown": "edited P1"}
        )

    mock_mcp.assert_not_called()


# ---------------------------------------------------------------------------
# Story 11.5 — Input quality detection (AC1/AC2/AC3)
# ---------------------------------------------------------------------------

_VALID_CATEGORIES = {
    "unsupported_content",
    "missing_expected_results",
    "missing_preconditions",
    "vague_language",
    "ambiguous_ui_reference",
    "insufficient_content",
}

_CLEAN_REQUIREMENT_MD = (
    "## Acceptance Criteria\n\n"
    "Given a logged-in user navigates to the dashboard\n"
    "Then all projects are listed with status indicators.\n"
    "Expected result: three project rows are visible.\n\n"
    "## Preconditions\n"
    "- Admin credentials must be stored in the user profile.\n"
    "- Backend server must be running on port 8000.\n"
    "The 'Logout' action completes within two seconds.\n"
)


def _assert_issue_fields(issue: dict) -> None:
    """Assert no None leakage and non-empty fields on a serialised QualityIssue dict."""
    assert issue["location"] and issue["location"] != "None"
    assert issue["message"] and issue["message"] != "None"
    assert issue["impact"] and issue["impact"] != "None"
    assert issue["category"] in _VALID_CATEGORIES


# --- 6.2: _detect_quality_issues (pure, sync) ---


def test_detect_quality_issues_clean_page_returns_empty(bob_agent: BobAgent) -> None:
    """Clean page with full content, expected results, preconditions → []."""
    page = {
        "page_title": "Login Flow",
        "requirement_md": _CLEAN_REQUIREMENT_MD,
        "warnings": [],
    }
    assert bob_agent._detect_quality_issues(page) == []


def test_detect_quality_issues_missing_expected_results(bob_agent: BobAgent) -> None:
    """No expected/then/result marker → missing_expected_results issue."""
    page = {
        "page_title": "No Expected",
        "requirement_md": (
            "Given setup is complete.\nWhen the form is submitted.\nThe action completes.\n"
        )
        + "A" * 200,
        "warnings": [],
    }
    issues = bob_agent._detect_quality_issues(page)
    categories = [qi.category for qi in issues]
    assert "missing_expected_results" in categories


def test_detect_quality_issues_missing_preconditions(bob_agent: BobAgent) -> None:
    """No precondition/given/setup marker → missing_preconditions issue."""
    page = {
        "page_title": "No Preconditions",
        "requirement_md": (
            "## Acceptance Criteria\n"
            "Expected: the page loads.\n"
            "Then the content appears.\n"
            "The result is visible.\n"
        )
        + "B" * 200,
        "warnings": [],
    }
    issues = bob_agent._detect_quality_issues(page)
    categories = [qi.category for qi in issues]
    assert "missing_preconditions" in categories


def test_detect_quality_issues_vague_language(bob_agent: BobAgent) -> None:
    """Page with 'etc.' and 'should work' yields vague_language issue listing the terms."""
    page = {
        "page_title": "Vague Story",
        "requirement_md": (
            "## Acceptance Criteria\n"
            "Given setup is complete\n"
            "Then it should work properly etc.\n"
            "Expected result: things complete as required.\n"
        )
        + "X" * 200,
        "warnings": [],
    }
    issues = bob_agent._detect_quality_issues(page)
    vague = [qi for qi in issues if qi.category == "vague_language"]
    assert len(vague) == 1
    assert "etc." in vague[0].message
    assert "should work" in vague[0].message


def test_detect_quality_issues_ambiguous_ui_reference(bob_agent: BobAgent) -> None:
    """Page with 'the button' yields ambiguous_ui_reference issue."""
    page = {
        "page_title": "Ambiguous UI",
        "requirement_md": (
            "## Acceptance Criteria\n"
            "Given setup is complete\n"
            "When the user clicks the button\n"
            "Then the field is updated.\n"
            "Expected result: changes saved.\n"
        )
        + "Y" * 200,
        "warnings": [],
    }
    issues = bob_agent._detect_quality_issues(page)
    ambiguous = [qi for qi in issues if qi.category == "ambiguous_ui_reference"]
    assert len(ambiguous) == 1
    assert "the button" in ambiguous[0].message


def test_detect_quality_issues_unsupported_content_fold(bob_agent: BobAgent) -> None:
    """Page warnings list is folded into unsupported_content issues."""
    page = {
        "page_title": "Diagram Page",
        "requirement_md": _CLEAN_REQUIREMENT_MD,
        "warnings": ["Gliffy diagram detected — manual review recommended"],
    }
    issues = bob_agent._detect_quality_issues(page)
    unsupported = [qi for qi in issues if qi.category == "unsupported_content"]
    assert len(unsupported) == 1
    assert "Gliffy diagram detected" in unsupported[0].message


def test_detect_quality_issues_insufficient_content(bob_agent: BobAgent) -> None:
    """Short requirement_md yields insufficient_content issue."""
    page = {
        "page_title": "Short Page",
        "requirement_md": "too short",
        "warnings": [],
    }
    issues = bob_agent._detect_quality_issues(page)
    categories = [qi.category for qi in issues]
    assert "insufficient_content" in categories


def test_detect_quality_issues_jira_page_scanned_same_way(bob_agent: BobAgent) -> None:
    """Jira page with short content is flagged (insufficient_content, missing markers)."""
    page = {
        "page_title": "[PROJ-1] Short Jira Ticket",
        "source_type": "jira",
        "requirement_md": "Short ticket",
        "warnings": [],
    }
    issues = bob_agent._detect_quality_issues(page)
    categories = [qi.category for qi in issues]
    assert "insufficient_content" in categories
    assert "missing_expected_results" in categories


def test_detect_quality_issues_no_none_leakage(bob_agent: BobAgent) -> None:
    """Every detected issue has non-empty location/message/impact and valid category."""
    pages: list[dict] = [
        {"page_title": "Short", "requirement_md": "x", "warnings": ["warn1"]},
        {"page_id": None, "page_title": None, "requirement_md": None, "warnings": None},
    ]
    for page in pages:
        for qi in bob_agent._detect_quality_issues(page):
            _assert_issue_fields(qi.to_dict())


# --- 6.3: _run_quality_detection summary and flag ---


@pytest.mark.asyncio
async def test_run_quality_detection_with_issues_returns_true_and_sends_warning(
    bob_agent: BobAgent,
) -> None:
    """AC2: pages with issues → True; every page has quality_issues key; warning sent."""
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "Flagged Page",
            "requirement_md": "too short",
            "warnings": [],
        },
        {
            "page_id": "p2",
            "page_title": "Clean Page",
            "requirement_md": _CLEAN_REQUIREMENT_MD,
            "warnings": [],
        },
    ]

    with patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send:
        result = await bob_agent._run_quality_detection()

    assert result is True
    for page in bob_agent.pages:
        assert "quality_issues" in page
    assert bob_agent.pages[1]["quality_issues"] == []

    warning_calls = [
        c for c in mock_send.call_args_list if c.kwargs.get("message_type") == "warning"
    ]
    assert len(warning_calls) == 1
    assert "Flagged Page" in warning_calls[0].kwargs["content"]
    assert (
        "impact" in warning_calls[0].kwargs["content"].lower()
        or "test" in warning_calls[0].kwargs["content"].lower()
        or "Too little" in warning_calls[0].kwargs["content"]
    )


@pytest.mark.asyncio
async def test_run_quality_detection_all_clean_returns_false(bob_agent: BobAgent) -> None:
    """AC2: all pages clean → False, quality_issues=[] per page, no warning sent."""
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "Clean Page",
            "requirement_md": _CLEAN_REQUIREMENT_MD,
            "warnings": [],
        },
    ]

    with patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send:
        result = await bob_agent._run_quality_detection()

    assert result is False
    assert bob_agent.pages[0]["quality_issues"] == []
    warning_calls = [
        c for c in mock_send.call_args_list if c.kwargs.get("message_type") == "warning"
    ]
    assert len(warning_calls) == 0


# --- 6.4: AC3 — approval records acknowledgement ---


def test_bob_handle_approve_records_quality_ack_with_issues(bob_agent: BobAgent) -> None:
    """Auto-save with quality issues records quality_warnings_acknowledged=True."""
    quality_issues = [
        {"category": "vague_language", "location": "P1", "message": "m", "impact": "i"}
    ]
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "P1",
            "source_url": "https://confluence.example.com/p1",
            "requirement_md": "x",
            "quality_issues": quality_issues,
        }
    ]

    with patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class:
        bob_agent._auto_save_requirements()

    mock_adapter = mock_adapter_class.return_value
    mock_adapter.save_metadata.assert_called_once()
    saved_path, saved_dict = mock_adapter.save_metadata.call_args[0]
    assert "p1" in saved_path
    assert saved_dict["quality_warnings_acknowledged"] is True
    assert saved_dict["acknowledged_quality_issues"] == quality_issues
    assert "acknowledged_at" in saved_dict


def test_bob_handle_approve_records_quality_ack_no_issues(bob_agent: BobAgent) -> None:
    """Auto-save with no quality issues records quality_warnings_acknowledged=False."""
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "P1",
            "source_url": "https://confluence.example.com/p1",
            "requirement_md": "x",
            "quality_issues": [],
        }
    ]

    with patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class:
        saved = bob_agent._auto_save_requirements()

    mock_adapter = mock_adapter_class.return_value
    mock_adapter.save_metadata.assert_called_once()
    _, saved_dict = mock_adapter.save_metadata.call_args[0]
    assert saved_dict["quality_warnings_acknowledged"] is False
    assert saved_dict["acknowledged_quality_issues"] == []
    assert saved == 1


# --- 6.5: Integration — detection runs inside _extract_descendants ---


@pytest.mark.asyncio
async def test_bob_extract_descendants_runs_quality_detection(bob_agent: BobAgent) -> None:
    """AC1 integration: quality_issues attached to pages; _has_quality_warnings set."""
    from datetime import UTC, datetime

    from ai_qa.pipelines.models import ConfluencePage, ParsedContent

    bob_agent._page_id = "12345"
    bob_agent._space_key = "TEST"

    assert bob_agent.project_context is not None
    assert bob_agent.project_context.artifact_service is not None
    bob_agent.project_context.artifact_service.db.get.side_effect = None
    mock_project = MagicMock()
    mock_project.confluence_base_url = "https://confluence.company.com"
    mock_project.jira_base_url = None
    bob_agent.project_context.artifact_service.db.get.return_value = mock_project

    mock_page = ConfluencePage(
        page_id="12345",
        title="Parent",
        content="<p>short</p>",
        space_key="TEST",
        url="https://confluence.company.com/x",
        retrieved_at=datetime.now(UTC),
    )
    parsed_content = ParsedContent(
        page_id="12345",
        page_title="Parent",
        source_url="https://confluence.company.com/x",
        markdown="short content",
        parsed_at=datetime.now(UTC),
    )

    mock_formatter = AsyncMock()
    mock_formatter.convert_markdown.return_value = "short"
    mock_parser = AsyncMock()
    mock_parser.parse.return_value = StageResult(
        success=True, data=parsed_content, errors=[], warnings=[], confidence=1.0
    )

    with (
        patch("ai_qa.agents.bob.MCPClient") as mock_mcp_client_class,
        patch("ai_qa.agents.bob.AppSettings"),
        patch("ai_qa.agents.bob.LLMClient"),
        patch("ai_qa.agents.bob.RequirementFormatter", return_value=mock_formatter),
        patch("ai_qa.agents.bob.ContentParser", return_value=mock_parser),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter"),
        patch("ai_qa.agents.bob.ConfluenceReader") as mock_reader_class,
        patch("ai_qa.agents.bob.JiraReader"),
        patch("ai_qa.agents.bob.get_user_secret", return_value="test-mcp-pat"),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
    ):
        mock_client = AsyncMock()
        mock_client.is_connected = True
        mock_mcp_client_class.return_value = mock_client

        mock_reader = AsyncMock()
        mock_reader.get_children_by_id.return_value = StageResult(
            success=True, data=[], errors=[], warnings=[], confidence=1.0
        )
        mock_reader.read_page_by_id.return_value = StageResult(
            success=True, data=mock_page, errors=[], warnings=[], confidence=1.0
        )
        mock_reader_class.return_value = mock_reader

        result = await bob_agent._extract_descendants("Parent")

    assert result.success is True
    assert len(bob_agent.pages) == 1
    assert "quality_issues" in bob_agent.pages[0]
    assert len(bob_agent.pages[0]["quality_issues"]) > 0
    assert bob_agent._has_quality_warnings is True
    # single-MCP-client invariant: detection adds no extra client
    assert mock_mcp_client_class.call_count == 1


# --- Point 5: interactive clarification loop -------------------------------


def _blocking_page(page_id: str, title: str = "P") -> dict:
    """A page dict carrying one BLOCKING quality issue (missing preconditions)."""
    return {
        "page_id": page_id,
        "page_title": title,
        "requirement_md": f"# {title}\n\nSome content.",
        "source_url": f"https://confluence.example.com/{page_id}",
        "source_type": "confluence",
        "quality_issues": [
            {
                "category": "missing_preconditions",
                "location": title,
                "message": "No preconditions or setup steps were found.",
                "impact": "i",
            }
        ],
    }


@pytest.mark.asyncio
async def test_begin_clarification_no_blocking_goes_to_select_id(bob_agent: BobAgent) -> None:
    """Advisory-only issues do not gate: Bob skips straight to id selection."""
    bob_agent.pages = [
        {
            "page_id": "p1",
            "page_title": "P1",
            "requirement_md": "x",
            "quality_issues": [
                {"category": "vague_language", "location": "P1", "message": "m", "impact": "i"}
            ],
        }
    ]
    bob_agent.output_files_saved = 1

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
    ):
        await bob_agent._begin_clarification_or_select()

    assert bob_agent.phase == "select_id"
    assert bob_agent._clarify_queue == []
    assert any(c.kwargs.get("metadata", {}).get("is_select_id") for c in mock_send.call_args_list)


@pytest.mark.asyncio
async def test_begin_clarification_with_blocking_enters_clarify(bob_agent: BobAgent) -> None:
    """A blocking issue starts the clarify loop and asks the first page."""
    bob_agent.pages = [_blocking_page("p1", "P1")]

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(
            bob_agent, "_plan_clarifications", new_callable=AsyncMock, return_value={"p1": "Q?"}
        ),
    ):
        await bob_agent._begin_clarification_or_select()

    assert bob_agent.phase == "clarify"
    assert bob_agent._clarify_queue == ["p1"]
    clarify_calls = [
        c
        for c in mock_send.call_args_list
        if c.kwargs.get("metadata", {}).get("type") == "clarify_request"
    ]
    assert len(clarify_calls) == 1
    assert clarify_calls[0].kwargs["metadata"]["page_id"] == "p1"
    # The question carries the unclear points for the panel.
    assert clarify_calls[0].kwargs["metadata"]["points"][0]["blocking"] is True


@pytest.mark.asyncio
async def test_clarify_answer_clears_page_then_prompts_select_id(bob_agent: BobAgent) -> None:
    """A successful answer that clears the page advances to id selection.

    _apply_clarification now re-scans + persists internally, so the test double
    simulates a clearing rewrite by emptying the page's quality_issues.
    """
    bob_agent.pages = [_blocking_page("p1", "P1")]
    bob_agent.phase = "clarify"
    bob_agent._clarify_queue = ["p1"]
    bob_agent.output_files_saved = 1

    async def fake_apply(page: dict, answer: str) -> bool:
        page["quality_issues"] = []  # clarification resolved the blocking issue
        return True

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock),
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(bob_agent, "_apply_clarification", side_effect=fake_apply) as mock_apply,
    ):
        await bob_agent.handle_approve(
            {"action": "clarify_answer", "page_id": "p1", "answer": "Users must be logged in."}
        )

    mock_apply.assert_awaited_once()
    assert bob_agent.phase == "select_id"
    assert bob_agent._clarify_queue == []


@pytest.mark.asyncio
async def test_clarify_empty_answer_errors_and_stays(bob_agent: BobAgent) -> None:
    """A blank answer is rejected without editing or advancing."""
    bob_agent.pages = [_blocking_page("p1", "P1")]
    bob_agent.phase = "clarify"
    bob_agent._clarify_queue = ["p1"]

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(bob_agent, "_apply_clarification", new_callable=AsyncMock) as mock_apply,
    ):
        await bob_agent.handle_approve(
            {"action": "clarify_answer", "page_id": "p1", "answer": "   "}
        )

    mock_apply.assert_not_awaited()
    assert bob_agent.phase == "clarify"
    assert bob_agent._clarify_queue == ["p1"]
    # content is positional arg 0 on every send_message call; assert on it directly.
    assert any(
        bool(c.args) and "Please type an answer" in c.args[0] for c in mock_send.call_args_list
    )


@pytest.mark.asyncio
async def test_clarify_skip_file_advances_to_next_page(bob_agent: BobAgent) -> None:
    """Skip this file drops it from the queue and asks the next page."""
    bob_agent.pages = [_blocking_page("p1", "P1"), _blocking_page("p2", "P2")]
    bob_agent.phase = "clarify"
    bob_agent._clarify_queue = ["p1", "p2"]

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(
            bob_agent, "_compose_clarify_question", new_callable=AsyncMock, return_value="Q?"
        ),
    ):
        await bob_agent.handle_approve({"action": "skip_file", "page_id": "p1"})

    assert bob_agent._clarify_queue == ["p2"]
    assert bob_agent.phase == "clarify"
    clarify_calls = [
        c
        for c in mock_send.call_args_list
        if c.kwargs.get("metadata", {}).get("type") == "clarify_request"
    ]
    assert clarify_calls[-1].kwargs["metadata"]["page_id"] == "p2"


@pytest.mark.asyncio
async def test_clarify_max_rounds_proceeds_without_blocking_forever(bob_agent: BobAgent) -> None:
    """When the page still has blocking issues after the round cap, Bob proceeds."""
    bob_agent.pages = [_blocking_page("p1", "P1")]
    bob_agent.phase = "clarify"
    bob_agent._clarify_queue = ["p1"]
    bob_agent._clarify_rounds = {"p1": _MAX_CLARIFY_ROUNDS - 1}
    bob_agent.output_files_saved = 1

    async def fake_apply(page: dict, answer: str) -> bool:
        # The rewrite did NOT resolve the blocking issue.
        page["quality_issues"] = [
            {"category": "missing_preconditions", "location": "P1", "message": "m", "impact": "i"}
        ]
        return True

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock),
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(bob_agent, "_apply_clarification", side_effect=fake_apply),
    ):
        await bob_agent.handle_approve(
            {"action": "clarify_answer", "page_id": "p1", "answer": "still not enough"}
        )

    # Hit the cap → did NOT re-ask the same page forever; moved on to select_id.
    assert bob_agent._clarify_rounds["p1"] == _MAX_CLARIFY_ROUNDS
    assert bob_agent.phase == "select_id"
    assert bob_agent._clarify_queue == []


@pytest.mark.asyncio
async def test_clarify_still_blocking_under_cap_reasks_same_page(bob_agent: BobAgent) -> None:
    """Still-blocking under the round cap re-asks the SAME page (does not advance)."""
    bob_agent.pages = [_blocking_page("p1", "P1")]
    bob_agent.phase = "clarify"
    bob_agent._clarify_queue = ["p1"]
    bob_agent._clarify_rounds = {}

    async def fake_apply(page: dict, answer: str) -> bool:
        page["quality_issues"] = [
            {"category": "missing_preconditions", "location": "P1", "message": "m", "impact": "i"}
        ]
        return True

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(bob_agent, "_apply_clarification", side_effect=fake_apply),
        patch.object(
            bob_agent, "_compose_clarify_question", new_callable=AsyncMock, return_value="Q?"
        ),
    ):
        await bob_agent.handle_approve(
            {"action": "clarify_answer", "page_id": "p1", "answer": "partial"}
        )

    assert bob_agent.phase == "clarify"
    assert bob_agent._clarify_queue == ["p1"]
    clarify_calls = [
        c
        for c in mock_send.call_args_list
        if c.kwargs.get("metadata", {}).get("type") == "clarify_request"
    ]
    assert clarify_calls[-1].kwargs["metadata"]["page_id"] == "p1"


@pytest.mark.asyncio
async def test_begin_clarification_excludes_failed_and_stub_pages(bob_agent: BobAgent) -> None:
    """Failed-conversion (empty md) and anti-hallucination stub pages never enter the
    clarify loop, so it cannot resurrect/fabricate a requirement extraction refused."""
    blocking = [
        {"category": "missing_preconditions", "location": "x", "message": "m", "impact": "i"}
    ]
    bob_agent.pages = [
        # Failed conversion: empty requirement_md (never auto-saved).
        {
            "page_id": "failed",
            "page_title": "Failed",
            "requirement_md": "",
            "quality_issues": blocking,
        },
        # Anti-hallucination stub: marked in warnings.
        {
            "page_id": "stub",
            "page_title": "Stub",
            "requirement_md": "# Stub\n\n_No extractable requirements were found._",
            "warnings": [
                "No extractable content on this page — "
                "requirement generation skipped (anti-hallucination guard)"
            ],
            "quality_issues": blocking,
        },
    ]
    bob_agent.output_files_saved = 0

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock),
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(bob_agent, "_plan_clarifications", new_callable=AsyncMock, return_value={}),
    ):
        await bob_agent._begin_clarification_or_select()

    # Neither page is clarifiable → no loop, straight to id selection.
    assert bob_agent._clarify_queue == []
    assert bob_agent.phase == "select_id"


@pytest.mark.asyncio
async def test_clarify_stale_answer_not_applied_to_other_page(bob_agent: BobAgent) -> None:
    """A clarify_answer whose page_id is not the queue head is NOT applied to a
    different requirement; the current head is simply re-asked (F2)."""
    bob_agent.pages = [_blocking_page("p1", "P1"), _blocking_page("p2", "P2")]
    bob_agent.phase = "clarify"
    bob_agent._clarify_queue = ["p1", "p2"]

    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(bob_agent, "_apply_clarification", new_callable=AsyncMock) as mock_apply,
        patch.object(
            bob_agent, "_compose_clarify_question", new_callable=AsyncMock, return_value="Q?"
        ),
    ):
        # page_id "p2" is in the queue but is NOT the head ("p1").
        await bob_agent.handle_approve(
            {"action": "clarify_answer", "page_id": "p2", "answer": "answer for p2"}
        )

    mock_apply.assert_not_awaited()  # never applied to the wrong page
    assert bob_agent._clarify_queue == ["p1", "p2"]
    clarify_calls = [
        c
        for c in mock_send.call_args_list
        if c.kwargs.get("metadata", {}).get("type") == "clarify_request"
    ]
    assert clarify_calls[-1].kwargs["metadata"]["page_id"] == "p1"  # re-asked the head


@pytest.mark.asyncio
async def test_apply_clarification_rescans_and_saves_fresh_warnings(bob_agent: BobAgent) -> None:
    """_apply_clarification re-scans the rewritten MD BEFORE saving, so the persisted
    warnings reflect the new content (F7) — a clearing rewrite saves warnings=[]."""
    page = {
        "page_id": "p1",
        "page_title": "P1",
        "source_url": "https://confluence.example.com/p1",
        "source_type": "confluence",
        "requirement_md": "too short",
        "quality_issues": [
            {"category": "missing_preconditions", "location": "P1", "message": "m", "impact": "i"}
        ],
    }

    fake_resp = MagicMock()
    fake_resp.content = _CLEAN_REQUIREMENT_MD  # a rewrite that clears all issues
    fake_client = MagicMock()
    fake_client._chat_model.ainvoke = AsyncMock(return_value=fake_resp)

    with (
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
        patch("ai_qa.agents.bob.LLMClient", return_value=fake_client),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter") as mock_adapter_class,
    ):
        ok = await bob_agent._apply_clarification(page, "Users must be logged in.")

    assert ok is True
    # _apply_clarification strips the LLM output before persisting.
    assert page["requirement_md"] == _CLEAN_REQUIREMENT_MD.strip()
    # Re-scan ran before save and cleared the issues; in-memory state matches.
    assert page["quality_issues"] == []
    # Persisted warnings are the FRESH (empty) set, not the stale blocking issue.
    save_kwargs = mock_adapter_class.return_value.save_requirement.call_args.kwargs
    assert save_kwargs["warnings"] == []


@pytest.mark.asyncio
async def test_apply_clarification_returns_false_on_llm_timeout(bob_agent: BobAgent) -> None:
    """A stalled provider must not hang the clarify loop: the LLM rewrite is bounded by
    _CLARIFY_LLM_TIMEOUT, so a slow call fails fast and _apply_clarification returns
    False (the caller then tells the user to skip/rephrase) instead of blocking."""
    page = {
        "page_id": "p1",
        "page_title": "P1",
        "source_url": "https://confluence.example.com/p1",
        "source_type": "confluence",
        "requirement_md": "too short",
        "quality_issues": [
            {"category": "missing_preconditions", "location": "P1", "message": "m", "impact": "i"}
        ],
    }

    async def _never_returns(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(30)  # far longer than the patched timeout

    fake_client = MagicMock()
    fake_client._chat_model.ainvoke = AsyncMock(side_effect=_never_returns)

    start = time.monotonic()
    with (
        patch("ai_qa.agents.bob._CLARIFY_LLM_TIMEOUT", 0.05),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
        patch("ai_qa.agents.bob.LLMClient", return_value=fake_client),
        patch("ai_qa.agents.bob.PipelineArtifactAdapter"),
    ):
        ok = await bob_agent._apply_clarification(page, "some answer")
    elapsed = time.monotonic() - start

    assert ok is False
    # Bounded by wait_for, not by the 30s sleep — proves the timeout actually fired.
    assert elapsed < 5.0
    # The in-memory MD is left unchanged (no partial/garbage rewrite persisted).
    assert page["requirement_md"] == "too short"


@pytest.mark.asyncio
async def test_compose_clarify_question_falls_back_to_template_on_timeout(
    bob_agent: BobAgent,
) -> None:
    """When the question-regeneration LLM call stalls, _compose_clarify_question returns
    the deterministic template question (never the sentinel, never a hang) so the user
    is always re-prompted and can answer or skip."""
    page = {
        "page_id": "p1",
        "page_title": "Login Page",
        "source_url": "https://confluence.example.com/p1",
        "source_type": "confluence",
        "requirement_md": "A requirement long enough to enter the clarify loop normally.",
        "quality_issues": [
            {
                "category": "missing_preconditions",
                "location": "Login Page",
                "message": "No preconditions or setup steps were found.",
                "impact": "i",
            }
        ],
    }

    async def _never_returns(*_args: object, **_kwargs: object) -> object:
        await asyncio.sleep(30)

    fake_client = MagicMock()
    fake_client._chat_model.ainvoke = AsyncMock(side_effect=_never_returns)

    start = time.monotonic()
    with (
        patch("ai_qa.agents.bob._CLARIFY_LLM_TIMEOUT", 0.05),
        patch.object(bob_agent, "get_llm_config", return_value=MagicMock()),
        patch("ai_qa.agents.bob.LLMClient", return_value=fake_client),
    ):
        question = await bob_agent._compose_clarify_question(page)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0
    # Falls back to the template — carries the title and the blocking gap, not the sentinel.
    assert "**Login Page** needs a bit more detail" in question
    assert "No preconditions or setup steps were found." in question
    assert not bob_agent._is_no_clarification(question)


@pytest.mark.asyncio
async def test_begin_clarification_uses_cross_page_plan_to_drop_files(bob_agent: BobAgent) -> None:
    """The holistic plan governs the queue: a flagged file whose gap is resolved
    elsewhere (so the planner omits it) never gets asked."""
    bob_agent.pages = [_blocking_page("p1", "P1"), _blocking_page("p2", "P2")]
    bob_agent.output_files_saved = 2

    # Planner keeps only p1 (p2's gap is covered by another file in the set).
    with (
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send,
        patch.object(bob_agent, "transition_to", new_callable=AsyncMock),
        patch.object(
            bob_agent,
            "_plan_clarifications",
            new_callable=AsyncMock,
            return_value={"p1": "Specific question about P1?"},
        ),
    ):
        await bob_agent._begin_clarification_or_select()

    assert bob_agent.phase == "clarify"
    assert bob_agent._clarify_queue == ["p1"]
    clarify_calls = [
        c
        for c in mock_send.call_args_list
        if c.kwargs.get("metadata", {}).get("type") == "clarify_request"
    ]
    assert len(clarify_calls) == 1
    assert clarify_calls[0].kwargs["metadata"]["page_id"] == "p1"
    assert clarify_calls[0].kwargs["content"] == "Specific question about P1?"


def test_parse_clarification_plan_extracts_only_valid_blocks(bob_agent: BobAgent) -> None:
    """The @@FILE/@@END plan format parses into {id: question}, dropping unknown ids."""
    text = (
        "@@FILE: p1\n"
        "What is the precondition for creating a journey?\n"
        "@@END\n"
        "@@FILE: p2\n"
        "What does success look like for the journey list?\n"
        "@@END\n"
        "@@FILE: unknown\n"
        "should be ignored\n"
        "@@END\n"
    )
    plan = bob_agent._parse_clarification_plan(text, {"p1", "p2"})
    assert set(plan.keys()) == {"p1", "p2"}
    assert plan["p1"] == "What is the precondition for creating a journey?"
    assert plan["p2"] == "What does success look like for the journey list?"


@pytest.mark.asyncio
async def test_bob_reprocess_provider_error_secret_safety(bob_agent: BobAgent) -> None:
    """Verify that a provider error in reprocess does not leak secret exception details."""
    bob_agent.pages = [{"page_id": "1", "page_title": "P1", "raw_html": "<p>x</p>"}]
    bob_agent.current_page_index = 0

    from ai_qa.ai_connection.config import LLMConfig

    with (
        patch("ai_qa.agents.bob.RequirementFormatter") as mock_formatter_class,
        patch.object(
            bob_agent,
            "get_llm_config",
            return_value=LLMConfig(provider="openai", api_key="sk-123", model_name="test"),
        ),
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send_message,
    ):
        mock_formatter = mock_formatter_class.return_value
        mock_formatter.convert_page = AsyncMock(
            side_effect=Exception("Provider failed with token secret_abc123")
        )

        res = await bob_agent.process({"action": "reprocess"}, feedback="fix it")

        assert res.success is True

        # Ensure the secret is not in any sent messages
        for call in mock_send_message.call_args_list:
            msg = call.args[0]
            assert "secret_abc123" not in msg

        # Ensure we sent a generic provider error warning
        warning_calls = [
            c.args[0] for c in mock_send_message.call_args_list if c.args[1] == "warning"
        ]
        assert any("provider error" in c for c in warning_calls)


@pytest.mark.asyncio
async def test_bob_reprocess_timeout_classification(bob_agent: BobAgent) -> None:
    """Verify that a timeout error is specifically classified."""
    bob_agent.pages = [{"page_id": "1", "page_title": "P1", "raw_html": "<p>x</p>"}]
    bob_agent.current_page_index = 0

    from ai_qa.ai_connection.config import LLMConfig

    with (
        patch("ai_qa.agents.bob.RequirementFormatter") as mock_formatter_class,
        patch.object(
            bob_agent,
            "get_llm_config",
            return_value=LLMConfig(provider="openai", api_key="sk-123", model_name="test"),
        ),
        patch.object(bob_agent, "send_message", new_callable=AsyncMock) as mock_send_message,
    ):
        mock_formatter = mock_formatter_class.return_value
        mock_formatter.convert_page = AsyncMock(side_effect=TimeoutError())

        await bob_agent.process({"action": "reprocess"}, feedback="fix it")

        warning_calls = [
            c.args[0] for c in mock_send_message.call_args_list if c.args[1] == "warning"
        ]
        assert any("timed out (model too slow)" in c for c in warning_calls)
