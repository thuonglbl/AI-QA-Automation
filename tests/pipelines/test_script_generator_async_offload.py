"""Regression test for Story 16.16: Sarah must not block the event loop.

The synchronous ``LLMClient.invoke`` is offloaded via ``asyncio.to_thread`` so a slow
on-premises call no longer freezes the single event loop (WebSocket + every HTTP route)
for the whole generation. The blocking call keeps its tenacity retry / typed-error
mapping by staying ``invoke`` — it just runs in a worker thread.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from ai_qa.models import TestCase, TestCaseStep
from ai_qa.pipelines.script_generator import ScriptGenerator


def _sample_test_case() -> TestCase:
    return TestCase(
        title="Login",
        steps=[TestCaseStep(number=1, action="Click login", target="login button")],
    )


async def test_call_llm_offloads_sync_invoke_to_thread(tmp_path: Path) -> None:
    generator = ScriptGenerator(output_base_dir=tmp_path)

    response = MagicMock()
    response.content = "def test_login(page):\n    pass\n"
    client = MagicMock()
    client.invoke = MagicMock(return_value=response)

    with (
        patch.object(generator, "_get_llm_client", return_value=client),
        patch(
            "ai_qa.pipelines.script_generator.asyncio.to_thread",
            wraps=asyncio.to_thread,
        ) as to_thread_spy,
    ):
        result = await generator._call_llm(_sample_test_case())

    # The blocking invoke was offloaded off the event loop, not run directly on it.
    assert to_thread_spy.called
    assert client.invoke.called
    assert "def test_login" in result
