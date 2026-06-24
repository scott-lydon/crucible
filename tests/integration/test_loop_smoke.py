"""Slice 12 spine: the loop drives the red passes through the target to Postgres.

POST /runs persists a run; the orchestrator Loop runs a black-box and a
white-box red pass (US-14) via a deterministic red double over the DummyTarget,
persists each attempt as an attack row, and marks the run complete. Real
Postgres, no LLM and no sandbox.

The registry here wires no oracles on purpose: this test covers the spine
(red to target to orchestrator to Postgres) without an LLM or a sandbox. The
oracle fan-out and verdict persistence are covered by test_loop_verdict.py with
deterministic oracle doubles, and the catch-rate metric by test_metrics.py.
"""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from modules.oracles.aggregator import VerdictAggregator
from modules.targets.dummy import DummyTarget
from orchestrator.loop import Loop
from orchestrator.wiring import Registry
from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack, Run
from shared.types import TargetType
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


async def test_both_passes_persist_attacks(client: AsyncClient, tmp_path: Path) -> None:
    resp = await client.post("/runs", json=_DUMMY_RUN)
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]

    red = ScriptedRed(
        [
            attempt("black-tactic", {"a": 1, "b": 2}, white_box=False),
            attempt("white-tactic", {"a": 3, "b": 4}, white_box=True),
        ]
    )
    registry = Registry(
        targets={TargetType.DUMMY: DummyTarget()},
        oracles=(),
        aggregator=VerdictAggregator(),
        red=red,
    )
    async with get_sessionmaker()() as session:
        await Loop(
            session=session, registry=registry, catalog_jsonl=tmp_path / "c.jsonl"
        ).run(run_id)

    async with get_sessionmaker()() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        assert run.status == "complete"

        attacks = (
            (await session.execute(select(Attack).where(Attack.run_id == run_id)))
            .scalars()
            .all()
        )
        assert {a.tactic for a in attacks} == {"black-tactic", "white-tactic"}
        assert {a.white_box for a in attacks} == {False, True}
        # Each attempt was driven through the target: the produced output rides
        # the attack audit trace.
        for a in attacks:
            assert "output" in a.audit_trace
