"""Red search unit tests: a sequenced LLM double over a fixture detector.

No network and no database: a fake LLM returns canned proposals in order and a
fixture target returns a fixed score, so the reason-propose-query-iterate loop,
the budget caps, the evasion threshold, and malformed-proposal handling are all
exercised deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.red import RedSearchAgent, parse_proposal
from shared.llm import LlmModel, LlmResult
from shared.types import (
    AttackBudget,
    AuditTrace,
    Money,
    ProbeResult,
    ProbeStatus,
    RunId,
    SealedSpec,
    TargetOutput,
    TargetType,
)


class _SequencedLlmClient:
    """Returns canned responses in order, so each iteration sees a new proposal."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        text = self._responses.pop(0)
        return LlmResult(
            text=text,
            model=model,
            dollars=Money.zero(),
            tokens_in=0,
            tokens_out=0,
            session_id="seq",
            raw={"seq": True},
        )


@dataclass(frozen=True, slots=True)
class _FixtureDetector:
    """A detector that scores every input the same, for deterministic evasion."""

    score: float = 0.1
    target_type: TargetType = TargetType.FRAUD
    display_name: str = "Fixture Detector"
    description: str = "Test fixture detector for the red search agent."
    artifact_ref: str = "fixture@v0"
    oracle_verified: bool = False

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> TargetOutput:
        return TargetOutput(
            output=attack_input, score=self.score, audit=AuditTrace(summary="fixture", steps=())
        )

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        return self.score

    async def self_test(self) -> ProbeResult:
        return ProbeResult(status=ProbeStatus.GREEN, detail={"score": self.score})


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "evade the detector",
            "obligations": [{"id": "o1", "description": "the transaction is fraudulent"}],
        }
    )


def _budget(attempts: int) -> AttackBudget:
    return AttackBudget(max_attempts=attempts, max_dollars=Money.of(1.0))


_THREE_TACTICS = [
    '{"tactic": "round-amount", "payload": {"amount": 100}, "reasoning": "round looks normal"}',
    '{"tactic": "micro-charge", "payload": {"amount": 3}, "reasoning": "tiny charges fly under"}',
    '{"tactic": "trusted-merchant", "payload": {"m": "coffee"}, "reasoning": "trusted seller"}',
]


async def test_finds_three_distinct_evasion_tactics() -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(_THREE_TACTICS))
    run_id = RunId.new()
    attacks = await agent.search(_spec(), _FixtureDetector(), _budget(3), run_id, white_box=False)

    assert len(attacks) == 3
    assert all(a.succeeded for a in attacks)
    assert len({a.tactic for a in attacks}) == 3
    assert all(a.run_id == run_id for a in attacks)
    assert all(a.white_box is False for a in attacks)


async def test_white_box_flag_threads_onto_every_attempt() -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(_THREE_TACTICS))
    attacks = await agent.search(
        _spec(), _FixtureDetector(), _budget(3), RunId.new(), white_box=True
    )
    assert all(a.white_box is True for a in attacks)


async def test_budget_caps_the_number_of_attempts() -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(_THREE_TACTICS + ["extra", "extra2"]))
    attacks = await agent.search(
        _spec(), _FixtureDetector(), _budget(2), RunId.new(), white_box=False
    )
    assert len(attacks) == 2


async def test_attempt_is_caught_when_score_is_above_threshold() -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(_THREE_TACTICS[:1]))
    attacks = await agent.search(
        _spec(), _FixtureDetector(score=0.9), _budget(1), RunId.new(), white_box=False
    )
    assert len(attacks) == 1
    assert attacks[0].succeeded is False


async def test_malformed_proposal_becomes_a_clean_failed_attempt() -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(["this is not JSON"]))
    attacks = await agent.search(
        _spec(), _FixtureDetector(), _budget(1), RunId.new(), white_box=False
    )
    assert len(attacks) == 1
    assert attacks[0].tactic == "malformed-proposal"
    assert attacks[0].succeeded is False


class _CapturingLlmClient:
    """Records the prompt and model of every call, returns one canned proposal."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.models: list[LlmModel] = []

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        self.prompts.append(prompt)
        self.models.append(model)
        return LlmResult(
            text=_THREE_TACTICS[0],
            model=model,
            dollars=Money.zero(),
            tokens_in=0,
            tokens_out=0,
            session_id="cap",
            raw={"cap": True},
        )


async def test_black_box_uses_sonnet_white_box_uses_opus() -> None:
    cap = _CapturingLlmClient()
    agent = RedSearchAgent(llm=cap)
    await agent.search(_spec(), _FixtureDetector(), _budget(1), RunId.new(), white_box=False)
    await agent.search(_spec(), _FixtureDetector(), _budget(1), RunId.new(), white_box=True)
    assert cap.models == [LlmModel.SONNET, LlmModel.OPUS]


async def test_oracle_scheme_is_injected_into_the_white_box_prompt() -> None:
    cap = _CapturingLlmClient()
    agent = RedSearchAgent(llm=cap)
    scheme = "Disclosed verification scheme:\n- held_out: generates fresh tests\n\n"
    await agent.search(
        _spec(),
        _FixtureDetector(),
        _budget(1),
        RunId.new(),
        white_box=True,
        oracle_scheme=scheme,
    )
    assert "Disclosed verification scheme" in cap.prompts[0]
    assert "held_out: generates fresh tests" in cap.prompts[0]


async def test_black_box_prompt_never_leaks_the_oracle_scheme() -> None:
    cap = _CapturingLlmClient()
    agent = RedSearchAgent(llm=cap)
    await agent.search(
        _spec(),
        _FixtureDetector(),
        _budget(1),
        RunId.new(),
        white_box=False,
        oracle_scheme="Disclosed verification scheme: SECRET",
    )
    assert "Disclosed verification scheme" not in cap.prompts[0]


def test_parse_proposal_accepts_a_well_formed_object() -> None:
    parsed = parse_proposal('{"tactic": "t", "payload": {"a": 1}, "reasoning": "r"}')
    assert parsed is not None
    assert parsed.tactic == "t"
    assert parsed.payload == {"a": 1}


def test_parse_proposal_unwraps_a_json_fence() -> None:
    parsed = parse_proposal('```json\n{"tactic": "t", "payload": {}, "reasoning": "r"}\n```')
    assert parsed is not None
    assert parsed.tactic == "t"


def test_parse_proposal_rejects_missing_or_wrong_typed_fields() -> None:
    assert parse_proposal('{"tactic": "t", "reasoning": "r"}') is None  # no payload
    assert parse_proposal('{"tactic": "", "payload": {}, "reasoning": "r"}') is None  # empty
    assert parse_proposal('{"tactic": "t", "payload": [], "reasoning": "r"}') is None  # list
    assert parse_proposal("not json") is None
