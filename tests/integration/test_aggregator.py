"""Slice-10 done criteria: the vote-weighted aggregator (four oracles 1 vote, judge
0.5, threshold 2.0); the loop persists a verdict per round with the full audit trace;
and a deterministic oracle replays to a byte-equal verdict (spec US-5)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

import asyncpg
from fastapi.testclient import TestClient

from modules.oracles.aggregator import aggregate, run_verdict
from modules.oracles.differential.oracle import FraudDifferentialOracle
from modules.targets.fraud.target import FraudTarget
from shared.datasets.fraud import load_splits
from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind, Shape, VerdictOutcome
from shared.types.ids import AttackId, RunId
from shared.types.sealed_spec import Obligation, SealedSpec
from tests.conftest import FRAUD_SPEC_YAML, PGHOST, PGPASSWORD, PGPORT, PGUSER, TEST_DB

_SPEC = SealedSpec(
    spec_id="s", target_kind="fraud", shape=Shape.shape1_ml,
    obligations=(Obligation("catch-fraud", "A fraudulent transaction must score high.",
                            "label_match", {}),),
    invariants=(), holdout_generator_kind="data_partition",
)


def _attack() -> Attack:
    return Attack(AttackId("a1"), RunId("r1"), 0, "t", {"amount": 1.0}, "", "seed")


def _vote(kind: OracleKind, fired: bool, weight: float) -> OracleVote:
    return OracleVote(kind, fired, weight, "obligation", "observation", "reason", "seed")


def test_aggregate_threshold_logic() -> None:
    atk = _attack()
    out: Mapping[str, Any] = {"label": 0}

    # Two independent oracles fire -> threshold met -> caught.
    caught = aggregate(RunId("r1"), atk, out,
                       [_vote(OracleKind.differential, True, 1.0),
                        _vote(OracleKind.held_out, True, 1.0)])
    assert caught.outcome is VerdictOutcome.caught
    assert caught.tally == 2.0 and caught.caught

    # One oracle + the half-vote judge = 1.5 < 2.0 -> clean (judge cannot decide).
    one_plus_judge = aggregate(RunId("r1"), atk, out,
                               [_vote(OracleKind.differential, True, 1.0),
                                _vote(OracleKind.llm_judge, True, 0.5)])
    assert one_plus_judge.tally == 1.5
    assert one_plus_judge.outcome is VerdictOutcome.clean

    # Judge alone -> clean.
    judge_only = aggregate(RunId("r1"), atk, out, [_vote(OracleKind.llm_judge, True, 0.5)])
    assert not judge_only.caught

    # Each oracle's reason is preserved verbatim in the audit trace (QA_ADVERSARY rule 3).
    assert caught.audit.detail["votes"][0]["reason"] == "reason"


async def _fetch_verdicts(run_id: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(host=PGHOST, port=PGPORT, user=PGUSER,
                                 password=PGPASSWORD, database=TEST_DB)
    try:
        rows = await conn.fetch(
            "SELECT outcome, tally, threshold, votes, audit_trace FROM verdicts "
            "WHERE run_id = $1 ORDER BY id", run_id)
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def test_loop_persists_a_verdict_per_round(client: TestClient) -> None:
    resp = client.post("/runs", json={
        "target_kind": "fraud", "shape": "shape1_ml", "spec_yaml": FRAUD_SPEC_YAML,
        "budget_rounds": 3, "budget_dollars": 1.0,
    })
    run_id = resp.json()["runId"]
    # poll
    import time
    for _ in range(100):
        if client.get(f"/runs/{run_id}").json()["status"] == "complete":
            break
        time.sleep(0.05)

    verdicts = asyncio.run(_fetch_verdicts(run_id))
    assert len(verdicts) == 3, verdicts
    for v in verdicts:
        assert v["threshold"] == 2.0
        # Only the differential oracle is wired so far (weight 1.0 < 2.0) -> all clean.
        assert v["outcome"] == "clean"
        votes = json.loads(v["votes"])
        assert any(vote["oracle"] == "differential" for vote in votes)
        assert json.loads(v["audit_trace"])["summary"]


def test_verdict_replays_byte_equal() -> None:
    oracle = FraudDifferentialOracle.load(1)
    target = FraudTarget.load(1)
    splits = load_splits()
    row = splits.x_holdout.iloc[0].to_dict()
    output = asyncio.run(target.submit(row)).output
    attack = Attack(AttackId("a"), RunId("r"), 0, "t", row, "", "seed")

    first = asyncio.run(run_verdict([oracle], _SPEC, attack, output))
    second = asyncio.run(run_verdict([oracle], _SPEC, attack, output))

    assert first.tally == second.tally
    assert first.outcome is second.outcome
    assert [v.as_dict() for v in first.votes] == [v.as_dict() for v in second.votes]
