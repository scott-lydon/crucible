"""Hybrid fallback: pure-LLM search fails three rounds, scipy then satisfies it.

No network: a sequenced LLM double returns three proposals the fixture detector
catches, then an optimization strategy; a constrained numeric search drives the
detector below the evasion threshold. Exercises the done-criterion trigger
(three failed rounds fire the fallback automatically) and the scipy executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.red import HybridSearch, RedSearchAgent, parse_strategy
from shared.llm import LlmModel, LlmResult
from shared.types import (
    AttackBudget,
    Money,
    ProbeResult,
    ProbeStatus,
    RunId,
    SealedSpec,
    TargetType,
)


class _SequencedLlmClient:
    """Returns canned responses in order, one per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        text = self._responses.pop(0)
        return LlmResult(
            text=text,
            model=model,
            dollars=Money.of(0.01),
            tokens_in=0,
            tokens_out=0,
            session_id="seq",
            raw={"seq": True},
        )


@dataclass(frozen=True, slots=True)
class _AmountDetector:
    """Scores any payload high unless its `amount` sits near 100.

    Hand-picked LLM proposals (no `amount`) are always caught at 1.0, so the
    pure-LLM search cannot win; the optimum at amount=100 scores ~0, reachable
    only by the numeric search. target_type is fraud so the value is a payload,
    not source code.
    """

    target_type: TargetType = TargetType.FRAUD
    display_name: str = "Amount Detector"
    description: str = "Test fixture detector used by the hybrid search tests."
    artifact_ref: str = "amount@v0"

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> Any:
        raise NotImplementedError  # the hybrid path only calls query_target

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        amount = attack_input.get("amount")
        if not isinstance(amount, (int, float)):
            return 1.0
        return min(1.0, abs(float(amount) - 100.0) / 200.0)

    async def self_test(self) -> ProbeResult:
        return ProbeResult(status=ProbeStatus.GREEN, detail={})


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "evade the detector",
            "obligations": [{"id": "o1", "description": "the transaction is fraudulent"}],
        }
    )


_THREE_CAUGHT = [
    '{"tactic": "merchant-swap", "payload": {"merchant": "coffee"}, "reasoning": "trusted"}',
    '{"tactic": "time-shift", "payload": {"hour": 3}, "reasoning": "off-peak"}',
    '{"tactic": "device-spoof", "payload": {"device": "known"}, "reasoning": "seen before"}',
]
_STRATEGY = (
    '{"variables": [{"name": "amount", "low": 0, "high": 500}], '
    '"fixed": {"merchant": "coffee"}, "reasoning": "sweep the amount band"}'
)


async def test_strategy_parse_accepts_and_rejects() -> None:
    good = parse_strategy(_STRATEGY)
    assert good is not None
    assert good.variables[0].name == "amount"
    assert good.fixed == {"merchant": "coffee"}
    assert parse_strategy('{"variables": [], "fixed": {}}') is None  # no variables
    assert parse_strategy('{"variables": [{"name": "x", "low": 5, "high": 1}]}') is None  # bad band
    assert parse_strategy("not json") is None


async def test_hybrid_executor_finds_an_evasion_with_scipy() -> None:
    hybrid = HybridSearch(llm=_SequencedLlmClient([_STRATEGY]))
    attack = await hybrid.execute(
        _spec(), _AmountDetector(), RunId.new(), transcript=[], white_box=False
    )
    assert attack.hybrid is True
    assert attack.tactic == "hybrid-numeric-search"
    assert attack.succeeded is True
    assert abs(float(attack.payload["amount"]) - 100.0) < 30.0
    assert attack.payload["merchant"] == "coffee"  # fixed field carried through


async def test_fallback_fires_automatically_after_three_failed_rounds() -> None:
    # One shared client, as in production: 3 caught proposals then the strategy.
    client = _SequencedLlmClient([*_THREE_CAUGHT, _STRATEGY])
    agent = RedSearchAgent(llm=client, hybrid=HybridSearch(llm=client))
    attacks = await agent.search(
        _spec(),
        _AmountDetector(),
        AttackBudget(max_attempts=4, max_dollars=Money.of(2.0)),
        RunId.new(),
        white_box=False,
    )
    # Three caught LLM rounds, then one hybrid attempt that evades.
    assert len(attacks) == 4
    assert [a.hybrid for a in attacks] == [False, False, False, True]
    assert all(a.succeeded is False for a in attacks[:3])
    assert attacks[3].succeeded is True
    assert attacks[3].tactic == "hybrid-numeric-search"


async def test_no_fallback_when_hybrid_is_not_wired() -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(list(_THREE_CAUGHT)))
    attacks = await agent.search(
        _spec(),
        _AmountDetector(),
        AttackBudget(max_attempts=3, max_dollars=Money.of(2.0)),
        RunId.new(),
        white_box=False,
    )
    assert len(attacks) == 3
    assert all(a.hybrid is False for a in attacks)
