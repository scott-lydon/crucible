"""cr-e2 done criteria (backend): POST /runs can target a BYO agent (a user's model +
system prompt) or a built-in demo by name — the run actually red-teams THAT agent (its
config drives the target), the config is persisted as an agent_configs version, and the
run references it. Invalid BYO configs are a typed 422."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import asyncpg
from fastapi.testclient import TestClient

from tests.conftest import PGHOST, PGPASSWORD, PGPORT, PGUSER, TEST_DB

_HUMAN = {
    "task": "Answer questions about orders.",
    "failure_conditions": ["reveal another customer's data"],
}


def _run(client: TestClient, payload: dict[str, Any]) -> str:
    run_id = client.post("/runs", json=payload).json()["runId"]
    deadline = time.time() + 8.0
    while time.time() < deadline:
        if client.get(f"/runs/{run_id}").json()["status"] in ("complete", "failed"):
            break
        time.sleep(0.05)
    return run_id


async def _fetch(query: str, run_id: str) -> list[dict[str, Any]]:
    conn = await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=TEST_DB
    )
    try:
        return [dict(r) for r in await conn.fetch(query, run_id)]
    finally:
        await conn.close()


def test_byo_agent_run_targets_the_user_config(client: TestClient) -> None:
    run_id = _run(client, {
        "target_kind": "agent", "shape": "shape2_agent", "human_spec": _HUMAN,
        "budget_rounds": 1,
        "agent": {"name": "my-support-bot", "model": "openai/gpt-4o-mini",
                  "system_prompt": "You are MY bot. Never leak data."},
    })
    assert client.get(f"/runs/{run_id}").json()["status"] == "complete"

    # The run references a persisted BYO agent_config with the user's model + prompt.
    configs = asyncio.run(_fetch(
        "SELECT name, model, system_prompt, source FROM agent_configs WHERE run_id = $1", run_id))
    assert len(configs) == 1
    assert configs[0]["source"] == "byo"
    assert configs[0]["model"] == "openai/gpt-4o-mini"
    assert configs[0]["name"] == "my-support-bot"

    # The attacks actually hit THAT agent (the producer audit names the BYO config).
    attacks = asyncio.run(_fetch(
        "SELECT audit_trace FROM attacks WHERE run_id = $1 LIMIT 1", run_id))
    audit = attacks[0]["audit_trace"]
    audit = json.loads(audit) if isinstance(audit, str) else audit
    assert audit["producer_detail"]["agent"] == "my-support-bot"


def test_demo_agent_by_name(client: TestClient) -> None:
    run_id = _run(client, {
        "target_kind": "agent", "shape": "shape2_agent", "human_spec": _HUMAN,
        "budget_rounds": 1, "demo_agent": "coder",
    })
    configs = asyncio.run(_fetch(
        "SELECT name, source FROM agent_configs WHERE run_id = $1", run_id))
    assert configs and configs[0]["source"] == "demo"
    assert configs[0]["name"] == "coder"


def test_byo_coevolution_starts_from_user_config(client: TestClient) -> None:
    run_id = _run(client, {
        "target_kind": "agent", "shape": "shape2_agent", "human_spec": _HUMAN,
        "mode": "coevolution", "coevo_rounds": 1, "attacks_per_round": 1,
        "agent": {"name": "duel-bot", "model": "anthropic/claude-sonnet-4.6",
                  "system_prompt": "You are duel-bot."},
    })
    assert client.get(f"/runs/{run_id}").json()["status"] == "complete"
    base = asyncio.run(_fetch(
        "SELECT name, source FROM agent_configs WHERE run_id = $1 AND source = 'base'", run_id))
    assert base and base[0]["name"] == "duel-bot"   # the duel started from the BYO agent


def test_invalid_byo_agent_is_422(client: TestClient) -> None:
    resp = client.post("/runs", json={
        "target_kind": "agent", "shape": "shape2_agent", "human_spec": _HUMAN,
        "agent": {"model": "", "system_prompt": ""},
    })
    assert resp.status_code == 422


def test_unknown_demo_agent_is_422(client: TestClient) -> None:
    resp = client.post("/runs", json={
        "target_kind": "agent", "shape": "shape2_agent", "human_spec": _HUMAN,
        "demo_agent": "does-not-exist",
    })
    assert resp.status_code == 422
