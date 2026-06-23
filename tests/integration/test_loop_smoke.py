"""Slice-1 done criteria: one loop round end to end through the orchestrator with
the dummy target — red proposes, the target scores, the attack persists with the
producer output, all against real Postgres."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import asyncpg
from fastapi.testclient import TestClient

from tests.conftest import (
    DUMMY_SPEC_YAML,
    PGHOST,
    PGPASSWORD,
    PGPORT,
    PGUSER,
    TEST_DB,
)


async def _fetch_attacks(run_id: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=TEST_DB
    )
    try:
        rows = await conn.fetch(
            "SELECT round_index, tactic, pillar, seed, payload, audit_trace "
            "FROM attacks WHERE run_id = $1 ORDER BY round_index",
            run_id,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def _poll_complete(client: TestClient, run_id: str, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        status = client.get(f"/runs/{run_id}").json()["status"]
        if status in ("complete", "failed"):
            return status
        time.sleep(0.05)
    return status


def test_one_round_with_dummy(client: TestClient) -> None:
    resp = client.post(
        "/runs",
        json={
            "target_kind": "dummy",
            "shape": "shape1_ml",
            "spec_yaml": DUMMY_SPEC_YAML,
            "budget_rounds": 2,
            "budget_dollars": 1.0,
        },
    )
    run_id = resp.json()["runId"]
    assert _poll_complete(client, run_id) == "complete"

    attacks = asyncio.run(_fetch_attacks(run_id))
    # 2 black-box rounds + 2 white-box self-test rounds (spec US-14).
    assert len(attacks) == 4, attacks
    assert [a["round_index"] for a in attacks] == [0, 1, 2, 3]
    assert all(a["tactic"] == "static-probe" for a in attacks)
    assert all(a["pillar"] == "red" for a in attacks)

    # Round 0 probe (amount=1500) scores fraudulent; round 1 (amount=25) does not.
    audit0 = json.loads(attacks[0]["audit_trace"])
    audit1 = json.loads(attacks[1]["audit_trace"])
    assert audit0["producer_output"]["label"] == 1
    assert audit0["producer_output"]["fraud_probability"] == 0.95
    assert audit1["producer_output"]["label"] == 0


def test_health_lists_dummy_and_red(client: TestClient) -> None:
    health = client.get("/health").json()
    assert health["targets/dummy"]["status"] == "green"
    assert health["red/static"]["status"] == "green"
