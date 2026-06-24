"""Slice 12 done-criterion: /metrics reports black-box and white-box catch rate.

Inserts a controlled set of judged attempts on real Postgres (some black-box,
some white-box) and asserts GET /metrics computes verifier recall for each box,
the gap between them, and the sanity property that white-box catch rate (recall
against an informed attacker) is at most the black-box rate. Also asserts the
empty state reports a null rate the dashboard renders as "Not yet measured"
(US-10), never a misleading 0.0.

These rows are an explicit, controlled fixture for the metric computation, not
fabricated measurements presented as a real run: the live end-to-end proof
(real red search both passes against the fraud model, real oracles) is the
opt-in test_white_box_live.py.
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
from shared.persistence.models import Run
from shared.persistence.models import Verdict as VerdictRow


async def _clear() -> None:
    async with get_sessionmaker()() as session:
        await session.execute(delete(VerdictRow))
        await session.execute(delete(AttackRow))
        await session.commit()


@pytest_asyncio.fixture
async def _clean_attacks(migrated_database: str) -> AsyncIterator[None]:
    """Clear judged attempts before the test so /metrics is deterministic.

    /metrics aggregates every attack and verdict in the database, so this test
    owns the table for its duration. Verdicts go first (they reference attacks).
    """
    await _clear()
    yield


def _run_row() -> Run:
    return Run(
        id=uuid.uuid4().hex,
        status="complete",
        target_type="fraud",
        artifact_ref="fraud-v1",
        spec_title="metrics fixture",
        spec_json={"title": "metrics fixture", "obligations": []},
        budget_max_attempts=8,
        budget_max_dollars=Decimal("1"),
        seed="seed",
    )


def _attack_row(run_id: str, *, white_box: bool, passed: bool) -> AttackRow:
    return AttackRow(
        id=uuid.uuid4().hex,
        run_id=run_id,
        tactic="t",
        payload={"a": 1},
        succeeded=passed,
        white_box=white_box,
        hybrid=False,
        pillar="red",
        dollars_spent=Decimal("0.01"),
        seed="seed",
        audit_trace={"summary": "fixture", "steps": []},
    )


def _verdict_row(run_id: str, attack_id: str, *, passed: bool) -> VerdictRow:
    return VerdictRow(
        id=uuid.uuid4().hex,
        run_id=run_id,
        attack_id=attack_id,
        passed=passed,
        tally=2.5 if passed else 1.0,
        votes=[],
        pillar="oracles",
        dollars_spent=Decimal("0"),
        seed="seed",
        audit_trace={"summary": "fixture", "steps": []},
        parent_action_id=attack_id,
    )


async def _insert(run_id: str, *, white_box: bool, passes: list[bool]) -> None:
    async with get_sessionmaker()() as session:
        for passed in passes:
            attack = _attack_row(run_id, white_box=white_box, passed=passed)
            session.add(attack)
            await session.flush()  # parent before child (verdict FK -> attacks.id)
            session.add(_verdict_row(run_id, attack.id, passed=passed))
        await session.commit()


async def test_metrics_empty_state_reports_not_yet_measured(
    client: AsyncClient, _clean_attacks: None
) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["black_box_catch_rate"]["rate"] is None
    assert body["white_box_catch_rate"]["rate"] is None
    assert body["catch_rate_gap"] is None


async def test_metrics_reports_both_catch_rates_and_gap(
    client: AsyncClient, _clean_attacks: None
) -> None:
    async with get_sessionmaker()() as session:
        run = _run_row()
        session.add(run)
        await session.commit()
        run_id = run.id

    # Black-box: 1 of 4 got past the ensemble -> catch rate 3/4 = 0.75.
    await _insert(run_id, white_box=False, passes=[True, False, False, False])
    # White-box (informed attacker): 3 of 4 got past -> catch rate 1/4 = 0.25.
    await _insert(run_id, white_box=True, passes=[True, True, True, False])

    resp = await client.get("/metrics")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    black = body["black_box_catch_rate"]
    white = body["white_box_catch_rate"]
    assert black["judged"] == 4
    assert black["caught"] == 3
    assert black["rate"] == 0.75
    assert white["judged"] == 4
    assert white["caught"] == 1
    assert white["rate"] == 0.25
    assert body["catch_rate_gap"] == 0.5
    # Sanity (US-14): the informed attacker is caught no more often than the
    # ignorant one, so white-box catch rate is at most the black-box rate.
    assert white["rate"] <= black["rate"]
