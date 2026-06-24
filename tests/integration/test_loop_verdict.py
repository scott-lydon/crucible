"""Slice 12 wiring: the loop drives each red attempt through the oracle ensemble.

Drives the orchestrator loop with two deterministic in-test oracles (a PASS
voter and a FAIL voter) over the DummyTarget, fed by a scripted red double, so
the red-to-target-to-oracles-to-aggregator-to-Postgres path is exercised on
real Postgres with no LLM and no sandbox. The live five-oracle path is covered
by each oracle's own opt-in run.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select

from modules.oracles.aggregator import VerdictAggregator
from modules.targets.dummy import DummyTarget
from orchestrator.loop import Loop
from orchestrator.wiring import Registry
from shared.persistence import get_sessionmaker
from shared.persistence.models import Verdict as VerdictRow
from shared.types import (
    OracleVote,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    TargetOutput,
    TargetType,
    VerdictDecision,
)
from tests.integration._red_double import ScriptedRed, attempt

_DUMMY_RUN = {
    "target_type": "dummy",
    "artifact_ref": "dummy-v0",
    "spec": {
        "title": "sum two integers",
        "obligations": [{"id": "o1", "description": "returns the sum of the two inputs"}],
        "invariants": [],
        "holdout_generator_kind": "llm_post_submit",
    },
    "budget": {"max_attempts": 3, "max_dollars": 1.0},
}


@dataclass(frozen=True, slots=True)
class _FixedOracle:
    """An oracle double that always casts the same vote (test infrastructure)."""

    name: str
    weight: float
    decision: VerdictDecision

    @property
    def protocol_description(self) -> str:
        return f"{self.name} fixed-vote test oracle"

    async def verify(
        self, spec: SealedSpec, attack_input: dict[str, Any], output: TargetOutput
    ) -> OracleVote:
        return OracleVote(
            oracle_name=self.name,
            decision=self.decision,
            weight=self.weight,
            reason=f"{self.name} fixed vote for the wiring test",
            obligation_id=spec.obligations[0].id if spec.obligations else None,
        )

    async def self_test(self) -> ProbeResult:
        return ProbeResult(status=ProbeStatus.GREEN, detail={"name": self.name})


async def test_loop_persists_one_verdict_per_attempt(
    client: AsyncClient, tmp_path: Path
) -> None:
    resp = await client.post("/runs", json=_DUMMY_RUN)
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]

    registry = Registry(
        targets={TargetType.DUMMY: DummyTarget()},
        oracles=(
            _FixedOracle("held_out", 1.0, VerdictDecision.PASS),
            _FixedOracle("metamorphic", 1.0, VerdictDecision.FAIL),
        ),
        aggregator=VerdictAggregator(),
        red=ScriptedRed([attempt("only-tactic", {"a": 1, "b": 2}, white_box=False)]),
    )

    async with get_sessionmaker()() as session:
        await Loop(
            session=session, registry=registry, catalog_jsonl=tmp_path / "c.jsonl"
        ).run(run_id)

    async with get_sessionmaker()() as session:
        verdicts = (
            (await session.execute(select(VerdictRow).where(VerdictRow.run_id == run_id)))
            .scalars()
            .all()
        )
        assert len(verdicts) == 1
        verdict = verdicts[0]
        # One PASS at 1.0 is below the 2.0 threshold, so the submission is caught.
        assert verdict.tally == 1.0
        assert verdict.passed is False
        assert len(verdict.votes) == 2
        assert {v["oracle_name"] for v in verdict.votes} == {"held_out", "metamorphic"}
        assert verdict.audit_trace["steps"][-1]["label"] == "tally"
        assert verdict.attack_id is not None
