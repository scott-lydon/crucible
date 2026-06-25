"""Slice 15: the dashboard's backend routes and the live SSE stream, on Postgres.

Covers the read routes the design pages fetch (run list/detail, verdict detail
with per-oracle drill-down, blue patch), the run-trigger guards, the SSE stream
emitting persisted rows, and that the verbatim design bundle is served with the
live sidecar injected. No LLM: rows are inserted directly, and the run-trigger's
background loop is stubbed so the route is tested without driving the real loop.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

import orchestrator.api as api
from shared.persistence import get_sessionmaker
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import (
    BluePatch,
    DifferentialRun,
    FuzzFinding,
    HoldoutRun,
    JudgeVote,
    ModelVersion,
    Run,
    Spec,
)
from shared.persistence.models import Verdict as VerdictRow

_RUN = {
    "target_type": "dummy",
    "artifact_ref": "dummy-v0",
    "spec": {
        "title": "sum two integers",
        "obligations": [{"id": "o1", "description": "returns the sum"}],
        "invariants": [],
        "holdout_generator_kind": "llm_post_submit",
    },
    "budget": {"max_attempts": 2, "max_dollars": 1.0},
}


def _run_row(status: str = "complete") -> Run:
    return Run(
        id=uuid.uuid4().hex,
        status=status,
        target_type="dummy",
        artifact_ref="dummy-v0",
        spec_title="t",
        spec_json={"title": "t", "obligations": []},
        budget_max_attempts=2,
        budget_max_dollars=Decimal("1"),
        seed="s",
    )


async def test_list_and_get_run(client: AsyncClient) -> None:
    created = await client.post("/runs", json=_RUN)
    run_id = created.json()["run_id"]

    listed = await client.get("/runs")
    assert listed.status_code == 200
    assert any(r["run_id"] == run_id for r in listed.json())

    detail = await client.get(f"/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["run_id"] == run_id
    assert body["attacks"] == []
    assert body["verdicts"] == []


async def test_get_verdict_returns_per_oracle_detail(client: AsyncClient) -> None:
    async with get_sessionmaker()() as session:
        run = _run_row()
        session.add(run)
        await session.flush()
        attack = AttackRow(
            id=uuid.uuid4().hex, run_id=run.id, tactic="t", payload={"a": 1},
            succeeded=False, white_box=False, hybrid=False, pillar="red",
            dollars_spent=Decimal("0"), seed="s", audit_trace={"summary": "x", "steps": []},
        )
        session.add(attack)
        await session.flush()
        verdict = VerdictRow(
            id=uuid.uuid4().hex, run_id=run.id, attack_id=attack.id, passed=False,
            tally=1.0, votes=[{"oracle_name": "llm_judge", "decision": "fail"}],
            pillar="oracles", dollars_spent=Decimal("0"), seed="s",
            audit_trace={"summary": "x", "steps": []}, parent_action_id=attack.id,
        )
        session.add(verdict)
        await session.flush()
        common = {"verdict_id": verdict.id, "run_id": run.id}
        session.add(JudgeVote(id=uuid.uuid4().hex, **common, decision="fail", weight=0.5,
                              reason="intent violated"))
        session.add(FuzzFinding(id=uuid.uuid4().hex, **common, decision="fail",
                                counterexample="f(0)=1", reason="property broke"))
        session.add(DifferentialRun(id=uuid.uuid4().hex, **common, decision="pass",
                                    reason="agreed", detail={}))
        await session.commit()
        rid, vid = run.id, verdict.id

    resp = await client.get(f"/runs/{rid}/verdicts/{vid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["judge_votes"][0]["reason"] == "intent violated"
    assert body["fuzz_findings"][0]["counterexample"] == "f(0)=1"
    assert body["differential_runs"][0]["decision"] == "pass"


async def test_get_blue_patch(client: AsyncClient) -> None:
    async with get_sessionmaker()() as session:
        patch = BluePatch(
            id=uuid.uuid4().hex, target_type="fraud", kind="retrain",
            detail={"provenance": ["a1"]}, provenance=["a1"], pillar="blue",
            dollars_spent=Decimal("0"), seed="s", audit_trace={"summary": "x", "steps": []},
        )
        session.add(patch)
        await session.flush()
        session.add(HoldoutRun(id=uuid.uuid4().hex, patch_id=patch.id, target_type="fraud",
                               holdout_size=5, detection_before=0.0, detection_after=0.6,
                               recovered=True, detail={}, seed="s"))
        session.add(ModelVersion(id=uuid.uuid4().hex, target_type="fraud", version=2,
                                 kind="retrain", artifact_ref="artifacts/fraud-v2.lgb",
                                 patch_id=patch.id, metrics={"auc": 0.87}))
        await session.commit()
        pid = patch.id

    resp = await client.get(f"/blue/{pid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["holdout_runs"][0]["recovered"] is True
    assert body["model_versions"][0]["version"] == 2


async def test_start_run_guards(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub the background loop so the route is tested without driving the real loop.
    async def _noop(run_id: str) -> None:
        return None

    monkeypatch.setattr(api, "_run_loop_background", _noop)

    assert (await client.post("/runs/does-not-exist/start")).status_code == 404

    created = await client.post("/runs", json=_RUN)
    run_id = created.json()["run_id"]
    started = await client.post(f"/runs/{run_id}/start")
    assert started.status_code == 202
    assert started.json()["status"] == "running"
    # Already running -> 409, never double-driven.
    assert (await client.post(f"/runs/{run_id}/start")).status_code == 409


async def test_sse_streams_persisted_rows(client: AsyncClient) -> None:
    async with get_sessionmaker()() as session:
        run = _run_row(status="complete")
        session.add(run)
        await session.flush()
        attack = AttackRow(
            id=uuid.uuid4().hex, run_id=run.id, tactic="t", payload={"a": 1},
            succeeded=True, white_box=False, hybrid=False, pillar="red",
            dollars_spent=Decimal("0"), seed="s", audit_trace={"summary": "x", "steps": []},
        )
        session.add(attack)
        await session.commit()
        rid = run.id

    async with client.stream("GET", f"/runs/{rid}/stream") as resp:
        assert resp.status_code == 200
        body = await resp.aread()
    text = body.decode("utf-8")
    assert "event: attack" in text
    assert "event: run_status" in text
    assert json.loads(text.split("event: attack\r\ndata: ")[1].split("\r\n")[0])["succeeded"]


async def test_root_redirects_to_app(client: AsyncClient) -> None:
    """A bare GET / returning 404 makes the URL look broken; / -> /app -> launcher.

    Asserted on the redirect chain rather than the final body so the test does
    not depend on the bundled dashboard page (covered separately below). Httpx
    does not follow redirects unless asked, so each hop is observed directly.
    """
    first = await client.get("/")
    assert first.status_code in (307, 308)
    assert first.headers["location"] == "/app"
    second = await client.get("/app")
    assert second.status_code in (307, 308)
    assert second.headers["location"] == "/app/Run%20Launcher.dc.html"


async def test_specs_history_returns_real_sealed_specs(client: AsyncClient) -> None:
    empty = await client.get("/specs/history")
    assert empty.status_code == 200
    assert isinstance(empty.json(), list)

    spec_id = f"spec-{uuid.uuid4().hex}"
    async with get_sessionmaker()() as session:
        session.add(
            Spec(
                id=spec_id,
                spec_json={
                    "title": "fraud spec",
                    "obligations": [{"id": "o1", "description": "d"}],
                },
            )
        )
        await session.commit()

    resp = await client.get("/specs/history")
    assert resp.status_code == 200
    rows = resp.json()
    assert isinstance(rows, list)
    row = next(r for r in rows if r["spec_id"] == spec_id)
    assert row["title"] == "fraud spec"
    assert row["obligations"] == 1
    assert row["created_at"]


async def test_design_bundle_served_with_live_sidecar(client: AsyncClient) -> None:
    page = await client.get("/app/slice-06-strategy-catalog.dc.html")
    assert page.status_code == 200
    assert "Strategy Catalog" in page.text  # verbatim UI served
    assert 'src="./live.js"' in page.text  # live wiring injected
    sidecar = await client.get("/app/live.js")
    assert sidecar.status_code == 200
    assert "CrucibleLive" in sidecar.text
    # Path traversal is refused.
    assert (await client.get("/app/../pyproject.toml")).status_code in (404, 400)


async def test_policy_returns_operative_halt_policy(client: AsyncClient) -> None:
    resp = await client.get("/policy")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["halt_recall_threshold"] is not None
    assert "recall" in body["operative_policy"]
    assert "custom_policy_yaml" in body


async def test_admin_overrides_is_a_list(client: AsyncClient) -> None:
    resp = await client.get("/admin/overrides")
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)
