"""Live test of the real `claude` CLI path.

Opt-in: runs only when CRUCIBLE_RUN_LLM_TESTS is set and the `claude` binary
is on PATH. This keeps it out of CI (no Max session there) and off every local
gate run (each call spends a few seconds and real quota), while still letting
us prove the real path on demand. No mock: this calls the live CLI.
"""

from __future__ import annotations

import os
import shutil

import pytest

from shared.llm import ClaudeCliClient, LlmModel

_should_run = os.environ.get("CRUCIBLE_RUN_LLM_TESTS") == "1" and shutil.which("claude")

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_LLM_TESTS=1 and have the claude CLI on PATH to run",
)


async def test_real_cli_returns_text_and_cost() -> None:
    client = ClaudeCliClient()
    result = await client.call("Reply with exactly the two characters: ok", model=LlmModel.SONNET)
    assert "ok" in result.text.lower()
    assert result.dollars.dollars >= 0
    assert "total_cost_usd" in result.raw
