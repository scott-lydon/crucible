"""B2: the halt rule is meaningful against a real-recall scenario (US-13).

The real-LLM e2e run (A1) measured white-box recall 0.0 against the fraud
detector (the Sonnet/Opus red agent evaded it on every attempt), which is below
HALT_RECALL_THRESHOLD (0.7), so the platform halts certification. This test
reproduces that condition with controlled rows on real Postgres (no LLM): when
the white-box pass records undetected attacks (recall below the red line), GET
/halt returns halted: true and a subsequent POST /runs is refused with 409.

These rows are an explicit fixture for the halt computation, not fabricated
measurements presented as a real run; the real end-to-end proof is the A1 script
and its committed artifacts/e2e_run_summary.json.
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
from shared.persistence.models import DifferentialRun, FuzzFinding, HaltState, JudgeVote, Run
from shared.persistence.models import Verdict as VerdictRow

_FRAUD_RUN = {
    "target_type": "fraud",
    "artifact_ref": "fraud-v1",
    "spec": {
        "title": "evade the fraud detector",
        "obligations": [{"id": "o1", "description": "fraud scored as legitimate"}],
    },
    "budget": {"max_attempts": 1, "max_dollars": 1.0},
}


@pytest_asyncio.fixture
async def _low_white_box_recall(migrated_database: str) -> AsyncIterator[None]:
    """Seed a white-box pass with undetected attacks (recall below the red line)."""
    async with get_sessionmaker()() as session:
        await session.execute(delete(JudgeVote))
        await session.execute(delete(FuzzFinding))
        await session.execute(delete(DifferentialRun))
        await session.execute(delete(VerdictRow))
        await session.execute(delete(AttackRow))
        await session.execute(delete(HaltState))
        # Runs are left in place (held_out_tests / model_versions reference them);
        # the halt recall is computed from attacks, which are cleared above, so
        # only this fixture's white-box attacks contribute.
        run = Run(
            id=uuid.uuid4().hex,
            status="complete",
            target_type="fraud",
            artifact_ref="fraud-v1",
            spec_title="halt fixture",
            spec_json={"title": "halt fixture", "obligations": []},
            budget_max_attempts=4,
            budget_max_dollars=Decimal("1"),
            seed="seed",
        )
        session.add(run)
        await session.flush()
        # White-box attacks that all evaded (undetected) -> recall 0.0 < 0.7.
        for _ in range(3):
            attack = AttackRow(
                id=uuid.uuid4().hex,
                run_id=run.id,
                tactic="evasion",
                payload={"Amount": 1.0},
                succeeded=True,
                white_box=True,
                hybrid=False,
                pillar="red",
                dollars_spent=Decimal("0.01"),
                seed="seed",
                audit_trace={"summary": "fixture", "steps": []},
            )
            session.add(attack)
            await session.flush()
            session.add(
                VerdictRow(
                    id=uuid.uuid4().hex,
                    run_id=run.id,
                    attack_id=attack.id,
                    passed=True,
                    tally=0.0,
                    votes=[],
                    pillar="oracles",
                    dollars_spent=Decimal("0"),
                    seed="seed",
                    audit_trace={"summary": "fixture", "steps": []},
                    parent_action_id=attack.id,
                )
            )
        await session.commit()
    yield
    # Teardown: clear the halt state and this fixture's rows so the persisted
    # halt does not block POST /runs in other tests sharing the database.
    async with get_sessionmaker()() as session:
        await session.execute(delete(VerdictRow))
        await session.execute(delete(AttackRow))
        await session.execute(delete(HaltState))
        await session.commit()


async def test_low_white_box_recall_halts_and_blocks_runs(
    client: AsyncClient, _low_white_box_recall: None
) -> None:
    halt = await client.get("/halt")
    assert halt.status_code == 200, halt.text
    body = halt.json()
    assert body["halted"] is True, body
    assert body["recall"] == 0.0, body
    assert body["recall"] < body["threshold"], body

    # With certification halted, a new run is refused.
    blocked = await client.post("/runs", json=_FRAUD_RUN)
    assert blocked.status_code == 409, blocked.text
