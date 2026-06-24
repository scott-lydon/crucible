"""Slice 13 live proof: real LLM proposes a strategy, scipy drives the model.

Opt-in (CRUCIBLE_RUN_LLM_TESTS=1 plus `claude` on PATH). Proves the hybrid
fallback end-to-end against the real fraud model: real Sonnet returns a usable
optimization strategy (not a refusal, the one failure only a live call catches),
and `scipy.optimize` then searches the proposed feature bands against the
committed LightGBM model. One LLM call plus synchronous model evaluations, so it
is fast relative to the search loop.
"""

from __future__ import annotations

import os
import shutil

import pytest

from modules.red import HybridSearch
from modules.targets.fraud import FraudTarget
from shared.llm import ClaudeCliClient
from shared.types import RunId, SealedSpec

_should_run = os.environ.get("CRUCIBLE_RUN_LLM_TESTS") == "1" and shutil.which("claude")

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_LLM_TESTS=1 and have the claude CLI on PATH to run",
)


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "sensitivity analysis of the credit-card fraud classifier",
            "obligations": [
                {
                    "id": "o1",
                    "description": (
                        "characterize how the classifier's score responds across "
                        "transaction-feature space; the model reads features named "
                        "Amount, Time, and V1 through V28"
                    ),
                }
            ],
        }
    )


async def test_real_strategy_then_scipy_executes_against_the_fraud_model() -> None:
    hybrid = HybridSearch(llm=ClaudeCliClient())
    attack = await hybrid.execute(
        _spec(), FraudTarget(), RunId.new(), transcript=[], white_box=False
    )

    assert attack.hybrid is True
    assert attack.tactic == "hybrid-numeric-search", (
        "the model returned no usable strategy (likely a refusal); "
        f"got tactic {attack.tactic!r}"
    )
    # scipy actually ran: the audit records a concrete best score from the model.
    search_step = next(s for s in attack.audit.steps if s.label == "numeric_search")
    assert isinstance(search_step.detail["best_score"], float)
