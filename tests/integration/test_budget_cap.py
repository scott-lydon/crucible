"""cr-f4 done criteria: the real-LLM cost meter + budget caps are enforced — a run halts
(not fails) when its per-run or the global dollar cap is reached, new runs are refused with
402 once the global cap is hit, and /budget reports the meter. This is the hard guard that
makes a public real-Claude run safe."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from modules.measure.budget import should_halt
from modules.targets.agent import AgentTarget
from orchestrator.wiring import get_container
from shared.llm import RecordingLLM
from shared.llm.client import LLMResult
from shared.types.agent import AgentConfig


def test_should_halt_logic() -> None:
    assert should_halt(1.0, 1.0, 0.0, 10.0) is not None          # per-run reached
    assert should_halt(0.5, 1.0, 0.0, 10.0) is None              # under both
    assert "global" in (should_halt(0.0, 1.0, 5.0, 5.0) or "")   # global reached
    assert should_halt(5.0, 0.0, 5.0, 0.0) is None               # caps of 0 = no cap


class _CostedLLM:
    model = "costed"
    available = True

    def __init__(self, per_call: float) -> None:
        self._d = per_call

    async def complete(self, system: str, prompt: str, *, max_tokens: int = 512) -> LLMResult:
        return LLMResult(text="I can help with that, safely.", model=self.model,
                         prompt_tokens=1, completion_tokens=1, dollars=self._d)


def _poll(client: TestClient, run_id: str) -> str:
    deadline = time.time() + 8.0
    status = ""
    while time.time() < deadline:
        status = client.get(f"/runs/{run_id}").json()["status"]
        if status in ("complete", "failed", "halted"):
            return status
        time.sleep(0.05)
    return status


def test_budget_caps_halt_run_and_refuse_new(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = get_container()
    orig_factory = container.agent_target_factory
    monkeypatch.setenv("CRUCIBLE_GLOBAL_BUDGET", "0.3")  # tiny global cap

    def costed_factory(cfg: AgentConfig) -> AgentTarget:
        return AgentTarget(RecordingLLM(_CostedLLM(0.5), "targets"), cfg, kind="agent")

    payload = {
        "target_kind": "agent", "shape": "shape2_agent", "demo_agent": "support-bot",
        "budget_rounds": 3, "budget_dollars": 0.4,
        "human_spec": {"task": "Help.", "failure_conditions": ["leak data"]},
    }
    try:
        container.agent_target_factory = costed_factory
        run_id = client.post("/runs", json=payload).json()["runId"]
        assert _poll(client, run_id) == "halted"          # the cap stopped it

        budget = client.get("/budget", params={"run_id": run_id}).json()
        assert budget["run_spent"] >= 0.4 or budget["global_exceeded"]
        assert budget["global_spent"] >= 0.3

        # Global cap now reached -> a new run is refused up front.
        assert client.post("/runs", json=payload).status_code == 402
    finally:
        container.agent_target_factory = orig_factory


def test_budget_endpoint_reports_meter(client: TestClient) -> None:
    b = client.get("/budget").json()
    assert "global_spent" in b and "global_cap" in b and "global_remaining" in b
    assert b["global_cap"] > 0
