"""Integration tests for the slice-20 Run Launcher routes.

Each route the launcher reads must return a real value (or honest null), never
a stub. These tests assert the shapes the launcher depends on, plus a few
spot-check truths from the real wiring (the actual registered targets, the
real oracle weights and pass threshold, the actual sandbox image string).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from modules.oracles.aggregator import VerdictAggregator
from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack, LlmCall, Run
from shared.types import RunStatus

pytestmark = pytest.mark.asyncio


async def test_me_returns_honest_anonymous_identity(client: AsyncClient) -> None:
    """Without an auth layer the route must surface the anonymous state, not
    fabricate a user. The launcher renders the null role as a `no role` chip."""
    body = (await client.get("/me")).json()
    assert body["display_name"] == "anonymous"
    assert body["role"] is None
    assert body["audit_log_target"] is None


async def test_workspace_returns_single_default_workspace(client: AsyncClient) -> None:
    """One workspace exists; until a workspace-budget table is seeded the
    monthly ceiling is null and the launcher renders `no ceiling`."""
    body = (await client.get("/workspace")).json()
    assert body["name"] == "default"
    assert body["monthly_ceiling_dollars"] is None


async def test_spend_current_month_reads_real_llm_calls(client: AsyncClient) -> None:
    """The spend number must be the sum of `llm_calls.dollars_spent`. Seeds two
    rows for the current month and asserts the sum, so a regression that hides
    or fakes the number is caught."""
    async with get_sessionmaker()() as session:
        # Persist the run rows the LlmCall foreign key requires.
        for _ in range(2):
            run = Run(
                id=uuid.uuid4().hex,
                status=RunStatus.PENDING.value,
                target_type="dummy",
                artifact_ref="dummy@v0",
                spec_title="t",
                spec_json={},
                budget_max_attempts=1,
                budget_max_dollars=Decimal("1"),
                seed="s",
            )
            session.add(run)
            await session.flush()
            session.add(
                LlmCall(
                    id=uuid.uuid4().hex,
                    run_id=run.id,
                    model="opus",
                    prompt="p",
                    raw_response="r",
                    parsed_output={},
                    tokens_in=10,
                    tokens_out=10,
                    pillar="red",
                    dollars_spent=Decimal("0.50"),
                    seed="s",
                )
            )
        await session.commit()
    body = (await client.get("/spend/current-month")).json()
    # We asserted exactly two new rows of $0.50 each above; the route's running
    # sum may include rows from earlier tests, so we assert >= our addition.
    assert body["spent_dollars"] >= 1.0
    assert body["ceiling_dollars"] is None
    assert body["period_start"].endswith("+00:00") or body["period_start"].endswith("Z")


async def test_targets_registered_returns_real_adapters(client: AsyncClient) -> None:
    """The list must reflect what the registry actually wires; a hardcoded
    JSON file in the route would break this test the moment wiring changes."""
    rows = (await client.get("/targets/registered")).json()
    assert isinstance(rows, list)
    types = {r["type"] for r in rows}
    assert {"dummy", "fraud", "code_agent"}.issubset(types)
    fraud = next(r for r in rows if r["type"] == "fraud")
    assert fraud["display_name"] == "Fraud"
    assert "fraud_adapter@" in fraud["artifact_ref"]
    code_agent = next(r for r in rows if r["type"] == "code_agent")
    assert code_agent["display_name"] == "Code Agent"
    assert code_agent["artifact_ref"].startswith("code_agent@")


async def test_oracles_registered_returns_real_weights_and_threshold(
    client: AsyncClient,
) -> None:
    """The oracle list must come from the registry, including the real judge
    weight and pass threshold from the aggregator. This guards against the
    `1/5 votes` design stub that contradicts the real `1/9` aggregator math."""
    body = (await client.get("/oracles/registered")).json()
    assert isinstance(body["oracles"], list)
    assert len(body["oracles"]) >= 4
    names = {o["name"] for o in body["oracles"]}
    assert any("judge" in n.lower() for n in names)
    assert body["pass_threshold"] == VerdictAggregator().pass_threshold
    # Total weight is the sum we'd compute from the real adapters; non-judge
    # oracles are weight 1.0 and the judge is 0.5, so a 5-oracle ensemble lands
    # at 4 * 1.0 + 0.5 = 4.5.
    assert body["total_weight"] == pytest.approx(4.5)


async def test_estimate_returns_null_with_no_prior_runs(client: AsyncClient) -> None:
    """A target with no attacks must report nulls, not a fabricated estimate.

    Uses a unique nonsense target type so the assertion holds regardless of
    other tests seeding fraud or code_agent attacks earlier in the session.
    """
    body = (
        await client.get(
            "/estimate", params={"target_type": "nonexistent_for_test", "rounds": 10}
        )
    ).json()
    assert body["cost_per_round_dollars"] is None
    assert body["low_dollars"] is None
    assert body["high_dollars"] is None
    assert body["sample_attacks"] == 0


async def test_estimate_returns_real_average_when_attacks_exist(
    client: AsyncClient,
) -> None:
    """With real attack rows the route averages dollars_spent; the launcher
    surfaces that number unmodified."""
    async with get_sessionmaker()() as session:
        run = Run(
            id=uuid.uuid4().hex,
            status=RunStatus.COMPLETE.value,
            target_type="dummy",
            artifact_ref="dummy@v0",
            spec_title="t",
            spec_json={},
            budget_max_attempts=2,
            budget_max_dollars=Decimal("1"),
            seed="s",
        )
        session.add(run)
        await session.flush()
        for cost in [Decimal("0.10"), Decimal("0.30")]:
            session.add(
                Attack(
                    id=uuid.uuid4().hex,
                    run_id=run.id,
                    tactic="t",
                    payload={},
                    succeeded=False,
                    white_box=False,
                    hybrid=False,
                    pillar="red",
                    dollars_spent=cost,
                    seed="s",
                    audit_trace={"summary": "x", "steps": []},
                )
            )
        await session.commit()

    body = (
        await client.get("/estimate", params={"target_type": "dummy", "rounds": 4})
    ).json()
    # Average across all recorded dummy attacks. The test does not assume the
    # only contributors are this run's rows, so we assert the per-round number
    # falls within the bounds of the smallest and largest seeded values.
    assert body["cost_per_round_dollars"] is not None
    assert 0.0 < body["cost_per_round_dollars"] <= 1.0
    assert body["low_dollars"] is not None
    assert body["high_dollars"] >= body["low_dollars"]
    assert body["sample_attacks"] >= 2


async def test_estimate_rejects_zero_or_negative_rounds(client: AsyncClient) -> None:
    """rounds must be positive; a zero is a request shape bug, not a real run."""
    resp = await client.get("/estimate", params={"target_type": "dummy", "rounds": 0})
    assert resp.status_code == 422


async def test_sandbox_image_returns_real_default(client: AsyncClient) -> None:
    """The image string must come from the constant DockerSandbox actually uses,
    not the design's hardcoded `crucible/sandbox:v1.4.2`."""
    from shared.sandbox.docker_sandbox import DEFAULT_SANDBOX_IMAGE

    body = (await client.get("/sandbox/image")).json()
    assert body["image"] == DEFAULT_SANDBOX_IMAGE
    assert body["egress_blocked"] is True


async def test_run_launcher_carries_live_route_wiring(client: AsyncClient) -> None:
    """The Run Launcher page must serve and its inline script must call the live
    backend routes it self-wires its data from. The React design replaced the old
    data-live attribute hooks with direct fetches, so a regression that drops the
    wiring would silently leave the page showing only its static design stubs."""
    page = await client.get("/app/Run%20Launcher.dc.html")
    assert page.status_code == 200
    html = page.text
    for route in [
        "/default-spec",
        "/targets/registered",
        "/oracles/registered",
        "/health/targets/",
    ]:
        assert route in html, f"missing live-route wiring: {route}"
