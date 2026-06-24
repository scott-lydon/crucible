"""Live-observability backend tests (US-8 / US-9 / US-2) — FREE, no real LLM.

`/health` returns the pillar -> module -> subcomponent hierarchy with per-leaf
state + timestamps; a self-test re-run updates a leaf; the seal card is present
(structure asserted regardless of Docker; the live probe is Docker-gated).
`/runs/{id}/stream` drives a deterministic synth run and asserts the SSE stream
emits attack + verdict + trace events and a terminal `complete`.

All in-memory SQLite, zero real LLM calls, no Postgres, no Docker required.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

import orchestrator.api as api
from modules.measure.health import HealthInputs
from orchestrator.api import app, init_db


class _StubOracle:
    """Minimal duck-typed oracle: has kind/vote/describe (shape smoke = green)."""

    def __init__(self, kind_value: str) -> None:
        self._kind = type("_K", (), {"value": kind_value})()

    @property
    def kind(self) -> object:
        return self._kind

    def vote(self, ctx: object) -> object:  # pragma: no cover - never called by smoke
        raise NotImplementedError

    def describe(self) -> str:  # pragma: no cover - never called by smoke
        return "stub"


class _StubDetector:
    def score(self, sample: object) -> float:  # pragma: no cover
        return 0.0


class _StubAdversary:
    def mutate(self, sample: object, score: float) -> object:  # pragma: no cover
        return None


_ORACLE_KINDS = (
    "held_out",
    "metamorphic",
    "invariant",
    "differential",
    "property_fuzz",
    "llm_judge",
)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    # Inject deterministic health inputs: stub in-process components + a
    # token-free anthropic ping that returns True. No Docker, no real LLM.
    api.HEALTH_TEST_INPUTS = HealthInputs(
        session_factory=api.session_factory(),
        detector=_StubDetector(),
        adversary=_StubAdversary(),
        oracles=[_StubOracle(k) for k in _ORACLE_KINDS],
        sandbox=None,
        anthropic_ping=lambda: True,
    )
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            yield c
    finally:
        api.HEALTH_TEST_INPUTS = None


def _all_leaves(body: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in body["pillars"]:
        for m in p["modules"]:
            for c in m["subcomponents"]:
                out[c["component_id"]] = c
    return out


async def test_health_returns_hierarchy_with_leaf_states(client: AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    # pillar -> module -> subcomponent shape.
    pillar_ids = {p["pillar_id"] for p in body["pillars"]}
    assert {"targets", "red", "blue", "measure", "external_deps"} <= pillar_ids
    leaves = _all_leaves(body)
    # Every oracle subcomponent is present.
    for kind in _ORACLE_KINDS:
        assert f"oracle.{kind}" in leaves
    # External deps present.
    for dep in ("dep.postgres", "dep.sandbox", "dep.anthropic"):
        assert dep in leaves
    # Every leaf is honest: a known state + a timestamp (or an error).
    for leaf in leaves.values():
        assert leaf["state"] in {"green", "amber", "red"}
        assert "last_self_test" in leaf and "error" in leaf
    # The in-process stubs smoke green; Postgres (SQLite) answers SELECT 1 green;
    # the token-free anthropic ping returns green.
    assert leaves["oracle.held_out"]["state"] == "green"
    assert leaves["targets.adapter.detector"]["state"] == "green"
    assert leaves["dep.postgres"]["state"] == "green"
    assert leaves["dep.anthropic"]["state"] == "green"
    assert leaves["dep.anthropic"]["last_self_test"] is not None


async def test_self_test_re_run_updates_leaf(client: AsyncClient) -> None:
    r = await client.post("/health/selftest/oracle.held_out")
    assert r.status_code == 200
    leaf = r.json()
    assert leaf["component_id"] == "oracle.held_out"
    assert leaf["state"] == "green"
    assert leaf["last_self_test"] is not None
    # Unknown component -> clean 404, never a fake leaf.
    miss = await client.post("/health/selftest/does.not.exist")
    assert miss.status_code == 404


async def test_seal_card_present_and_honest(client: AsyncClient) -> None:
    body = (await client.get("/health")).json()
    card = body["seal_card"]
    # Egress allow-list is EMPTY (the seal); env carries nothing; excludes named.
    assert card["egress_allow_list"] == []
    assert card["env"] == []
    assert card["network"] == "none"
    assert any("ANTHROPIC_API_KEY" in e for e in card["env_excludes"])
    assert any("Postgres" in e for e in card["env_excludes"])
    assert card["run_seal_probe_endpoint"] == "/health/seal-probe"


async def test_seal_probe_honest_when_no_sandbox(client: AsyncClient) -> None:
    # The injected inputs have sandbox=None -> the live probe is unavailable and
    # the endpoint says so honestly (never a fabricated sealed=true).
    r = await client.post("/health/seal-probe")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is False
    assert body["sealed"] is None
    assert body["reason"]


async def test_anthropic_check_is_token_free(client: AsyncClient) -> None:
    # With ping=False the anthropic leg goes red WITHOUT any network call.
    api.HEALTH_TEST_INPUTS = HealthInputs(
        session_factory=api.session_factory(),
        oracles=[_StubOracle(k) for k in _ORACLE_KINDS],
        anthropic_ping=lambda: False,
    )
    leaves = _all_leaves((await client.get("/health")).json())
    assert leaves["dep.anthropic"]["state"] == "red"


async def _collect_sse(client: AsyncClient, run_id: str) -> list[tuple[str, dict]]:
    """Consume the SSE stream into a list of (event, data) until `complete`."""
    import json

    events: list[tuple[str, dict]] = []
    async with client.stream("GET", f"/runs/{run_id}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        event_name = ""
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                events.append((event_name, json.loads(line[len("data: ") :])))
                if event_name == "complete":
                    break
    return events


async def test_stream_emits_attack_verdict_trace_and_complete(
    client: AsyncClient,
) -> None:
    # Drive a deterministic synth run (no real LLM); the loop persists rows.
    r = await client.post(
        "/runs",
        json={"target": "synth", "rounds": 5, "batch_size": 200,
              "seed": "seed-1", "run_blue": False},
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    # The background task completes within the request lifecycle under
    # ASGITransport, so by the time we stream the run is terminal — the tail
    # still emits every persisted attack/verdict/trace then `complete`.
    events = await _collect_sse(client, run_id)
    kinds = [e for e, _ in events]
    assert "attack" in kinds
    assert "trace" in kinds
    assert "verdict" in kinds
    assert kinds[-1] == "complete"
    # The terminal event reports a terminal status and is bounded (not timed out).
    complete = events[-1][1]
    assert complete["status"] in {"complete", "failed"}
    assert complete["timed_out"] is False
    # ASR-so-far accompanies attack events; detection-rate accompanies verdicts.
    attack_payloads = [d for e, d in events if e == "attack"]
    assert all("asr_so_far" in d for d in attack_payloads)
    verdict_payloads = [d for e, d in events if e == "verdict"]
    assert all("detection_rate_so_far" in d for d in verdict_payloads)
    # Trace events carry the rationale field (null for the deterministic mutator).
    trace_payloads = [d for e, d in events if e == "trace"]
    assert all("rationale" in d for d in trace_payloads)
