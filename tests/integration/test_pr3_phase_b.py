"""PR #3 -> main port, Phase B (oracle hardening).

B1 the LLM judge renders unparseable prose as an UNAVAILABLE vote (never a guessed
   violation), the unavailable vote contributes nothing to the tally, and the new
   ``available`` flag survives the A3 serialization round trip.

(B2 code-agent second-implementation differential and B3 per-oracle README protocol
descriptions are tracked separately; B2 is new feature work, not a verbatim port.)
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from modules.oracles.aggregator import aggregate, vote_as_json, vote_from_json
from modules.oracles.llm_judge.oracle import LLMJudgeOracle
from modules.oracles.protocol import oracle_protocols
from shared.llm.client import ScriptedLLM
from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind, Shape
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("c", "A fraudulent transaction must score high.", "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)
_ATTACK = Attack(AttackId("a"), RunId("r"), 0, "t", {"Amount": 1.0}, "", "seed")


def _judge(response: str) -> LLMJudgeOracle:
    return LLMJudgeOracle(ScriptedLLM(lambda _s, _p: response, model="scripted-judge"))


def test_b1_prose_yields_unavailable_not_violation() -> None:
    vote = asyncio.run(
        _judge("The output looks like a clear VIOLATION to me.").vote(_SPEC, _ATTACK, {"label": 0})
    )
    assert vote.fired is False
    assert vote.available is False


def test_b1_valid_json_still_available_and_fires() -> None:
    judge = _judge('{"verdict": "violation", "reason": "missed fraud"}')
    vote = asyncio.run(judge.vote(_SPEC, _ATTACK, {"label": 0}))
    assert vote.fired is True
    assert vote.available is True


def test_b1_available_flag_round_trips() -> None:
    unavailable = OracleVote(
        oracle=OracleKind.llm_judge, fired=False, weight=0.5, obligation="c",
        observation="unparseable", reason="judge response not parseable as JSON",
        seed="seed", available=False,
    )
    assert vote_from_json(vote_as_json(unavailable)) == unavailable
    assert vote_from_json(vote_as_json(unavailable)).available is False


def test_b1_unavailable_vote_contributes_nothing_to_tally() -> None:
    # A high-weight unavailable vote, were it ever to "fire", must not move the tally.
    unavailable = OracleVote(
        oracle=OracleKind.llm_judge, fired=False, weight=0.5, obligation="c",
        observation="unparseable", reason="unavailable", seed="seed", available=False,
    )
    verdict = aggregate(RunId("r"), _ATTACK, {"label": 0}, [unavailable])
    assert verdict.tally == 0.0
    assert verdict.caught is False


# ----------------------------- B3 -----------------------------

def test_b3_protocols_cover_five_kinds_with_first_paragraph() -> None:
    protos = oracle_protocols()
    kinds = [p["kind"] for p in protos]
    assert kinds == ["held_out", "metamorphic", "differential", "property_fuzz", "llm_judge"]
    for p in protos:
        assert p["name"] and not p["name"].startswith("#")  # README H1, heading stripped
        assert len(p["description"]) > 40                    # first paragraph, non-empty


def test_b3_api_serves_oracle_protocols(client: TestClient) -> None:
    rows = client.get("/oracle-protocols").json()
    assert [r["kind"] for r in rows] == [
        "held_out", "metamorphic", "differential", "property_fuzz", "llm_judge"
    ]
    assert all(r["description"] for r in rows)
