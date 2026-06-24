"""Slice 16 done-criterion: the corpus JSONL row count equals the table count.

Inserts successful and caught attacks on real Postgres, then asserts GET /corpus
counts only the successful (undetected) ones and GET /corpus.jsonl streams exactly
that many lines, each in the US-11 shape. The test owns the attack tables for its
duration (the database persists across runs).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import DifferentialRun, FuzzFinding, JudgeVote, Run
from shared.persistence.models import Verdict as VerdictRow


@pytest_asyncio.fixture(autouse=True)
async def _clean(migrated_database: str) -> AsyncIterator[None]:
    async with get_sessionmaker()() as session:
        for model in (JudgeVote, FuzzFinding, DifferentialRun, VerdictRow, AttackRow):
            await session.execute(delete(model))
        await session.commit()
    yield


async def _seed(client: AsyncClient, n_success: int, n_caught: int) -> str:
    run = Run(
        id=uuid.uuid4().hex, status="complete", target_type="fraud",
        artifact_ref="fraud-v1", spec_title="t",
        spec_json={"title": "t", "obligations": []}, budget_max_attempts=8,
        budget_max_dollars=Decimal("1"), seed="s",
    )
    async with get_sessionmaker()() as session:
        session.add(run)
        await session.flush()
        for i in range(n_success + n_caught):
            session.add(
                AttackRow(
                    id=uuid.uuid4().hex, run_id=run.id, tactic=f"t{i}", payload={"amount": i},
                    succeeded=i < n_success, white_box=False, hybrid=False, pillar="red",
                    dollars_spent=Decimal("0.02"), seed="s",
                    audit_trace={"summary": "x", "steps": []},
                )
            )
        await session.commit()
    return run.id


async def test_corpus_jsonl_count_equals_table_count(client: AsyncClient) -> None:
    await _seed(client, n_success=5, n_caught=3)

    table = await client.get("/corpus")
    assert table.status_code == 200, table.text
    body = table.json()
    assert body["count"] == 5  # only undetected (succeeded) attacks
    assert len(body["rows"]) == 5

    download = await client.get("/corpus.jsonl")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    lines = [ln for ln in download.text.splitlines() if ln.strip()]
    assert len(lines) == body["count"]  # exact equality is the done-criterion

    record = json.loads(lines[0])
    assert set(record) == {
        "attack_id", "target_type", "tactic", "prompt", "audit_trace", "dollars", "captured_at"
    }
    assert record["target_type"] == "fraud"


async def test_corpus_empty_when_no_successful_attacks(client: AsyncClient) -> None:
    await _seed(client, n_success=0, n_caught=4)
    table = await client.get("/corpus")
    assert table.json()["count"] == 0
    download = await client.get("/corpus.jsonl")
    assert [ln for ln in download.text.splitlines() if ln.strip()] == []
