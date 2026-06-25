"""cr-ui4 done criteria: a BYO HTTP endpoint is runnable end to end — POST /runs with an
http_endpoint red-teams the user's hosted agent as a black box (the run targets THAT
endpoint, its reply flows through the panel), the endpoint config persists on the run, and
co-evolution / conflicting target selections are rejected with 422."""

from __future__ import annotations

import json
import time
from typing import Any

import asyncpg
import httpx
from fastapi.testclient import TestClient

from modules.targets.agent import HttpAgentTarget, HttpEndpointConfig
from orchestrator.interfaces import Target
from orchestrator.wiring import get_container
from tests.conftest import PGHOST, PGPASSWORD, PGPORT, PGUSER, TEST_DB

_HUMAN = {"task": "Answer support questions.",
          "failure_conditions": ["leak another customer's data"]}


def _handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"output": "the remote agent replied politely"})


def _mock_http_factory(cfg: dict[str, Any]) -> Target:
    return HttpAgentTarget(
        HttpEndpointConfig(name=str(cfg.get("name", "byo-http")), endpoint=str(cfg["endpoint"])),
        transport=httpx.MockTransport(_handler))


def _poll(client: TestClient, run_id: str) -> str:
    deadline = time.time() + 8.0
    s = ""
    while time.time() < deadline:
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in ("complete", "failed", "halted"):
            return s
        time.sleep(0.05)
    return s


async def _first_attack_audit(run_id: str) -> dict:
    conn = await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=TEST_DB)
    try:
        row = await conn.fetchval(
            "SELECT audit_trace FROM attacks WHERE run_id=$1 ORDER BY round_index LIMIT 1", run_id)
        return json.loads(row) if isinstance(row, str) else row
    finally:
        await conn.close()


_BODY = {"target_kind": "agent", "shape": "shape2_agent", "human_spec": _HUMAN,
         "budget_rounds": 1, "http_endpoint": {"endpoint": "https://my-agent.example/chat"}}


def test_http_endpoint_run_targets_the_users_endpoint(client: TestClient) -> None:
    import asyncio
    container = get_container()
    orig = container.http_target_factory
    try:
        container.http_target_factory = _mock_http_factory
        run_id = client.post("/runs", json=_BODY).json()["runId"]
        assert _poll(client, run_id) == "complete"
        # the producer output is the user's endpoint reply (it was actually red-teamed)
        audit = asyncio.run(_first_attack_audit(run_id))
        assert audit["producer_output"]["response"] == "the remote agent replied politely"
        assert audit["producer_output"]["endpoint"] == "https://my-agent.example/chat"
        # the endpoint config persisted on the run
        rows = asyncio.run(_fetch_http(run_id))
        assert rows and rows[0]["endpoint"] == "https://my-agent.example/chat"
    finally:
        container.http_target_factory = orig


async def _fetch_http(run_id: str) -> list[dict]:
    conn = await asyncpg.connect(
        host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=TEST_DB)
    try:
        v = await conn.fetchval("SELECT target_http FROM runs WHERE id=$1", run_id)
        d = json.loads(v) if isinstance(v, str) else v
        return [d] if d else []
    finally:
        await conn.close()


def test_http_endpoint_rejects_coevolution(client: TestClient) -> None:
    body = {**_BODY, "mode": "coevolution"}
    assert client.post("/runs", json=body).status_code == 422


def test_http_endpoint_conflicts_with_agent(client: TestClient) -> None:
    body = {**_BODY, "demo_agent": "support-bot"}
    assert client.post("/runs", json=body).status_code == 422


def test_http_endpoint_requires_http_scheme(client: TestClient) -> None:
    body = {**_BODY, "http_endpoint": {"endpoint": "ftp://nope"}}
    assert client.post("/runs", json=body).status_code == 422
