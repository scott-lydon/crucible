"""Slice 11 live proof: real Sonnet attacks the real fraud detector.

Opt-in (CRUCIBLE_RUN_LLM_TESTS=1 plus `claude` on PATH), since it calls the
real CLI and loads the committed LightGBM model. No mocks: the red agent
proposes real transactions, the real model scores them, and the search records
the evasions it finds. Proves the reason-propose-query-iterate loop runs
end-to-end against a live target.
"""

from __future__ import annotations

import os
import shutil

import pytest

from modules.red import RedSearchAgent
from modules.targets.fraud import FraudTarget
from shared.llm import ClaudeCliClient
from shared.types import AttackBudget, Money, RunId, SealedSpec

_should_run = os.environ.get("CRUCIBLE_RUN_LLM_TESTS") == "1" and shutil.which("claude")

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_LLM_TESTS=1 and have the claude CLI on PATH to run",
)


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "evade the credit-card fraud detector",
            "obligations": [
                {
                    "id": "o1",
                    "description": (
                        "the transaction is fraudulent but should be scored as "
                        "legitimate by the detector; propose transaction feature "
                        "values (Amount, Time, V1..V28) as the payload"
                    ),
                }
            ],
        }
    )


async def test_real_red_agent_finds_distinct_evasions_on_the_fraud_model() -> None:
    agent = RedSearchAgent(llm=ClaudeCliClient())
    attacks = await agent.search(
        _spec(),
        FraudTarget(),
        AttackBudget(max_attempts=5, max_dollars=Money.of(2.0)),
        RunId.new(),
        white_box=False,
    )

    distinct_successful = {a.tactic for a in attacks if a.succeeded}
    assert len(distinct_successful) >= 3, (
        f"expected at least 3 distinct successful evasion tactics; "
        f"got {len(distinct_successful)}: {sorted(distinct_successful)}"
    )
