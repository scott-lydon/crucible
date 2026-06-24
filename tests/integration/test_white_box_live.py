"""Slice 12 live proof: real white-box red attacks the real fraud detector.

Opt-in (CRUCIBLE_RUN_LLM_TESTS=1 plus `claude` on PATH). Proves the new
white-box behavior end-to-end against a live target and a live model:

  - the informed pass runs on Opus 4.8 (the strongest model, US-14),
  - the disclosed oracle scheme is injected into the prompt, and
  - the model returns real, parseable proposals rather than refusing.

The refusal path is the one only a live call catches (QA_ADVERSARY.md / the
red-search research-prompt gotcha): a new prompt shape (scheme + Opus) could
trip a refusal that the parser would log as a malformed proposal, so this
asserts at least one attempt parsed into a real tactic.
"""

from __future__ import annotations

import os
import shutil

import pytest

from modules.red import RedSearchAgent, compose_white_box_brief
from modules.targets.fraud import FraudTarget
from shared.llm import ClaudeCliClient, LlmModel
from shared.types import AttackBudget, Money, RunId, SealedSpec

_should_run = os.environ.get("CRUCIBLE_RUN_LLM_TESTS") == "1" and shutil.which("claude")

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_LLM_TESTS=1 and have the claude CLI on PATH to run",
)

_SCHEME = compose_white_box_brief(
    [
        ("held_out", "generates fresh assertions from the sealed spec post-submit"),
        ("metamorphic", "checks transformation relations with no reference answer"),
        ("differential", "compares a second-family implementation on shared inputs"),
        ("property_fuzz", "random-samples inputs and asserts spec properties"),
        ("llm_judge", "an Opus judge reads the artifact and votes at half weight"),
    ]
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


async def test_white_box_red_runs_on_opus_with_the_scheme_and_does_not_refuse() -> None:
    agent = RedSearchAgent(llm=ClaudeCliClient())
    attacks = await agent.search(
        _spec(),
        FraudTarget(),
        AttackBudget(max_attempts=2, max_dollars=Money.of(2.0)),
        RunId.new(),
        white_box=True,
        oracle_scheme=_SCHEME,
    )

    assert attacks, "the white-box search returned no attempts at all"
    assert all(a.white_box for a in attacks)
    real = [a for a in attacks if a.tactic != "malformed-proposal"]
    assert real, (
        "every white-box attempt was a malformed proposal; the model likely "
        "refused the scheme-injected prompt. Tactics: "
        f"{[a.tactic for a in attacks]}"
    )
    # The white-box pass is pinned to Opus 4.8 (US-14).
    assert agent.white_box_model is LlmModel.OPUS
