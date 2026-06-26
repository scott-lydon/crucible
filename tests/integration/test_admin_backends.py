"""cr-e4 done criteria: the remaining dashboard backends serve live data — deterministic
replay+diff of a verdict, spec history, the leaderboard, and the admin/debug summary."""

from __future__ import annotations

import time

import asyncpg
from fastapi.testclient import TestClient

from tests.conftest import PGHOST, PGPASSWORD, PGPORT, PGUSER, TEST_DB

_AGENT_RUN = {
    "target_kind": "agent", "shape": "shape2_agent", "budget_rounds": 1,
    "human_spec": {"task": "Help with orders.", "failure_conditions": ["leak customer data"]},
}


def _run(client: TestClient, payload: dict = _AGENT_RUN) -> str:  # type: ignore[assignment]
    run_id = client.post("/runs", json=payload).json()["runId"]
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if client.get(f"/runs/{run_id}").json()["status"] in ("complete", "failed"):
            break
        time.sleep(0.05)
    return run_id


async def _first_attack(run_id: str) -> str:
    conn = await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=TEST_DB)
    try:
        return str(await conn.fetchval(
            "SELECT id FROM attacks WHERE run_id = $1 ORDER BY round_index LIMIT 1", run_id))
    finally:
        await conn.close()


def test_replay_is_deterministic_and_identical(client: TestClient) -> None:
    import asyncio
    run_id = _run(client)
    attack_id = asyncio.run(_first_attack(run_id))
    replay = client.get(f"/attacks/{attack_id}/replay").json()
    assert replay["attackId"] == attack_id
    # Deterministic oracles (mock) -> the replay reproduces the stored verdict byte-for-byte.
    assert replay["identical"] is True
    assert replay["replayed"]["outcome"] == replay["stored"]["outcome"]
    assert client.get("/attacks/nope/replay").status_code == 404


def test_spec_history_shows_compiled_obligations_and_source(client: TestClient) -> None:
    run_id = _run(client)
    history = client.get("/spec-history", params={"run_id": run_id}).json()
    assert len(history) == 1
    entry = history[0]
    assert entry["compiler"] == "deterministic"
    assert entry["source_text"]["task"].startswith("Help with orders")
    assert any("leak customer data" in o["description"] for o in entry["obligations"])


def test_leaderboard_lists_runs(client: TestClient) -> None:
    run_id = _run(client)
    board = client.get("/leaderboard").json()
    assert any(row["runId"] == run_id for row in board)
    for row in board:
        assert "agent" in row and "target_kind" in row and "white_box_recall" in row


def test_debug_summary(client: TestClient) -> None:
    _run(client)
    debug = client.get("/debug").json()
    assert debug["totals"]["runs"] >= 1
    assert debug["totals"]["attacks"] >= 1
    assert "llm_dollars_total" in debug
    assert "runs_by_status" in debug
    assert "health" in debug
