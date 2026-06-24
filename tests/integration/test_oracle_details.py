"""Slice 15: the loop persists per-oracle detail rows the verdict view renders.

Drives the loop with a scripted red double and fixed oracles named for the three
per-oracle tables, then asserts a judge_votes, fuzz_findings, and differential_runs
row was written for the verdict. Real Postgres, no LLM, no sandbox.
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
from shared.persistence.models import DifferentialRun, FuzzFinding, JudgeVote
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

_RUN = {
    "target_type": "dummy",
    "artifact_ref": "dummy-v0",
    "spec": {
        "title": "sum",
        "obligations": [{"id": "o1", "description": "returns the sum"}],
        "invariants": [],
        "holdout_generator_kind": "llm_post_submit",
    },
    "budget": {"max_attempts": 2, "max_dollars": 1.0},
}


@dataclass(frozen=True, slots=True)
class _FixedOracle:
    name: str
    weight: float
    decision: VerdictDecision

    @property
    def protocol_description(self) -> str:
        return f"{self.name} test oracle"

    async def verify(
        self, spec: SealedSpec, attack_input: dict[str, Any], output: TargetOutput
    ) -> OracleVote:
        return OracleVote(
            oracle_name=self.name, decision=self.decision, weight=self.weight,
            reason=f"{self.name} said {self.decision.value}", obligation_id="o1",
        )

    async def self_test(self) -> ProbeResult:
        return ProbeResult(status=ProbeStatus.GREEN, detail={})


async def test_loop_writes_judge_fuzz_and_differential_rows(
    client: AsyncClient, tmp_path: Path
) -> None:
    run_id = (await client.post("/runs", json=_RUN)).json()["run_id"]

    registry = Registry(
        targets={TargetType.DUMMY: DummyTarget()},
        oracles=(
            _FixedOracle("llm_judge", 0.5, VerdictDecision.FAIL),
            _FixedOracle("property_fuzz", 1.0, VerdictDecision.FAIL),
            _FixedOracle("differential", 1.0, VerdictDecision.PASS),
            _FixedOracle("held_out", 1.0, VerdictDecision.PASS),
        ),
        aggregator=VerdictAggregator(),
        red=ScriptedRed([attempt("only", {"a": 1}, white_box=False)]),
    )
    async with get_sessionmaker()() as session:
        await Loop(session=session, registry=registry, catalog_jsonl=tmp_path / "c.jsonl").run(
            run_id
        )

    async with get_sessionmaker()() as session:
        judge = (
            (await session.execute(select(JudgeVote).where(JudgeVote.run_id == run_id)))
            .scalars()
            .all()
        )
        fuzz = (
            (await session.execute(select(FuzzFinding).where(FuzzFinding.run_id == run_id)))
            .scalars()
            .all()
        )
        diff = (
            (await session.execute(select(DifferentialRun).where(DifferentialRun.run_id == run_id)))
            .scalars()
            .all()
        )
    assert len(judge) == 1 and judge[0].decision == "fail" and judge[0].weight == 0.5
    assert len(fuzz) == 1 and fuzz[0].counterexample == "property_fuzz said fail"
    assert len(diff) == 1 and diff[0].decision == "pass"
