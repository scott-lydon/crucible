"""Slice 1 done-criterion: one loop round end to end with the DummyTarget.

POST /runs persists a run, the orchestrator Loop drives a probe through the
wired target, and the result is persisted as an attack row with the run marked
complete. Real Postgres, no mocks.

The registry here wires the DummyTarget with no oracles on purpose: this test
covers the spine (target to orchestrator to Postgres) without an LLM or a
sandbox, as its docstring promised before slice 10 added the oracle-verify
step. The loop's oracle fan-out and verdict persistence are covered by
test_loop_verdict.py with deterministic oracle doubles.
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select

from modules.oracles.aggregator import VerdictAggregator
from modules.targets.dummy import DummyTarget
from orchestrator.loop import Loop
from orchestrator.wiring import Registry
from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack, Run
from shared.types import TargetType

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


async def test_one_round_with_dummy(client: AsyncClient) -> None:
    resp = await client.post("/runs", json=_DUMMY_RUN)
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["run_id"]

    registry = Registry(
        targets={TargetType.DUMMY: DummyTarget()},
        oracles=(),
        aggregator=VerdictAggregator(),
    )
    async with get_sessionmaker()() as session:
        await Loop(session=session, registry=registry).run(run_id)

    async with get_sessionmaker()() as session:
        run = await session.get(Run, run_id)
        assert run is not None
        assert run.status == "complete"

        attacks = (
            await session.execute(select(Attack).where(Attack.run_id == run_id))
        ).scalars().all()
        assert len(attacks) == 1
        attack = attacks[0]
        assert attack.tactic == "seed-probe"
        assert attack.audit_trace["output"]["echo"]["probe"] == "seed"
        assert attack.audit_trace["score"] is not None
