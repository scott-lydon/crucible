"""Slice 18 done-criterion: dropping white-box recall halts certification (US-13).

Seeds white-box verdicts on real Postgres, then asserts that when recall falls
below the red line GET /halt reports the banner text and a launch (POST /runs) is
refused with HTTP 409 and a typed body; and that above the line the platform is
not halted and a launch is accepted. The test owns the attack tables so the
global white-box recall is deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import (
    DifferentialRun,
    FuzzFinding,
    HaltState,
    JudgeVote,
    Run,
)
from shared.persistence.models import Verdict as VerdictRow

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


@pytest_asyncio.fixture(autouse=True)
async def _clean(migrated_database: str) -> AsyncIterator[None]:
    async with get_sessionmaker()() as session:
        for model in (JudgeVote, FuzzFinding, DifferentialRun, VerdictRow, AttackRow, HaltState):
            await session.execute(delete(model))
        await session.commit()
    yield


async def _seed_white_box(caught: int, total: int) -> None:
    """Insert `total` white-box judged attacks, `caught` of them caught."""
    async with get_sessionmaker()() as session:
        run = Run(
            id=uuid.uuid4().hex, status="complete", target_type="fraud",
            artifact_ref="fraud-v1", spec_title="t",
            spec_json={"title": "t", "obligations": []}, budget_max_attempts=8,
            budget_max_dollars=Decimal("1"), seed="s",
        )
        session.add(run)
        await session.flush()
        for i in range(total):
            attack = AttackRow(
                id=uuid.uuid4().hex, run_id=run.id, tactic="t", payload={"a": i},
                succeeded=i >= caught, white_box=True, hybrid=False, pillar="red",
                dollars_spent=Decimal("0"), seed="s",
                audit_trace={"summary": "x", "steps": []},
            )
            session.add(attack)
            await session.flush()
            session.add(VerdictRow(
                id=uuid.uuid4().hex, run_id=run.id, attack_id=attack.id,
                passed=i >= caught, tally=1.0, votes=[], pillar="oracles",
                dollars_spent=Decimal("0"), seed="s",
                audit_trace={"summary": "x", "steps": []}, parent_action_id=attack.id,
            ))
        await session.commit()


async def test_low_recall_halts_and_refuses_launch(client: AsyncClient) -> None:
    # 1 of 4 white-box attacks caught -> recall 0.25, below the 0.70 red line.
    await _seed_white_box(caught=1, total=4)

    halt = await client.get("/halt")
    assert halt.status_code == 200
    body = halt.json()
    assert body["halted"] is True
    assert body["recall"] == 0.25
    assert body["threshold"] == 0.7
    assert body["message"] == "Certification halted: recall is 0.25, threshold is 0.70"

    launch = await client.post("/runs", json=_RUN)
    assert launch.status_code == 409, launch.text
    assert launch.json()["detail"]["halted"] is True


async def test_recall_above_red_line_does_not_halt(client: AsyncClient) -> None:
    # All 4 white-box attacks caught -> recall 1.0, above the red line.
    await _seed_white_box(caught=4, total=4)

    halt = await client.get("/halt")
    assert halt.json()["halted"] is False
    assert halt.json()["recall"] == 1.0

    launch = await client.post("/runs", json=_RUN)
    assert launch.status_code == 201, launch.text


async def test_no_runs_means_no_halt(client: AsyncClient) -> None:
    # No white-box verdicts: recall is unmeasured, so the platform is not halted.
    halt = await client.get("/halt")
    assert halt.json()["halted"] is False
    assert halt.json()["recall"] is None
    assert (await client.post("/runs", json=_RUN)).status_code == 201
