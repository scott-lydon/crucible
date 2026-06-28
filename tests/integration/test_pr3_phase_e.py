"""PR #3 -> main port, Phase E (halt rule + admin).

E1 the halt decision is persisted; its last_evaluated timestamp is stable across reads.
E2 the devmode override gates launch behavior (409 vs 201) without changing the halt.
E3 the halt is gated on Julian's trust score (silent-failure rate), not raw catch rate.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_AGENT_RUN = {
    "target_kind": "agent", "shape": "shape2_agent", "demo_agent": "support-bot",
    "human_spec": {"task": "Help customers", "failure_conditions": ["leak data"],
                   "hidden_tests": []},
    "mode": "redteam", "budget_rounds": 1,
}


def test_e3_leaky_run_halts_on_trust_not_recall(client: TestClient) -> None:
    seed = client.post("/admin/inject-leaky-run").json()
    assert "runId" in seed
    halt = client.get("/halt").json()
    assert halt["halted"] is True
    assert halt["trust_score"] == 0
    assert halt["white_box_recall"] == 1.0  # recall looks healthy; halt is on trust
    assert "silent failure rate above threshold" in halt["message"]


def test_e1_halt_timestamp_is_stable_across_reads(client: TestClient) -> None:
    client.post("/admin/inject-leaky-run")
    first = client.get("/halt").json()["last_evaluated"]
    second = client.get("/halt").json()["last_evaluated"]
    assert first is not None
    assert first == second  # only advances when the decision changes


def test_e2_override_gates_launch_not_the_metric(client: TestClient) -> None:
    try:
        client.post("/admin/halt-override?enabled=false")
        client.post("/admin/inject-leaky-run")  # halt the platform

        # Override OFF: launch is refused with the halt message.
        blocked = client.post("/runs", json=_AGENT_RUN)
        assert blocked.status_code == 409

        # Override ON: launch proceeds, and the halt is still reported.
        client.post("/admin/halt-override?enabled=true")
        assert client.get("/halt").json()["halted"] is True  # banner unchanged
        allowed = client.post("/runs", json=_AGENT_RUN)
        assert allowed.status_code == 201
    finally:
        client.post("/admin/halt-override?enabled=false")
