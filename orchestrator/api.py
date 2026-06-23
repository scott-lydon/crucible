"""FastAPI surface. Slice 0: ``POST /runs``, ``GET /health``, ``GET /runs/{id}`` and
the SSE stream. The dashboard (deferred) is a thin client over these endpoints; the
API is the product surface every other slice verifies through."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from modules.measure.corpus import export_corpus
from modules.measure.metrics import compute_metrics
from modules.measure.report import sr_11_7_markdown
from orchestrator.loop import create_run, run_loop
from orchestrator.wiring import get_container
from shared.persistence.db import session_scope
from shared.persistence.models import AttackRow, Run, VerdictRow
from shared.telemetry.log import configure_logging
from shared.types.core import AttackBudget, TargetSpec
from shared.types.enums import RunStatus
from shared.types.ids import RunId
from shared.types.sealed_spec import SealedSpec

# Background loop tasks, kept referenced so they are not garbage-collected mid-run.
_background: set[asyncio.Task[None]] = set()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(json_output=False)
    yield


app = FastAPI(title="Crucible", version="0.1.0", lifespan=_lifespan)


class RunRequest(BaseModel):
    target_kind: str = Field(examples=["fraud"])
    shape: str = Field(examples=["shape1_ml"])
    spec_yaml: str
    budget_rounds: int = Field(default=5, ge=1, le=200)
    budget_dollars: float = Field(default=2.0, ge=0.0)


class RunAccepted(BaseModel):
    runId: str  # noqa: N815 — matches the dashboard's /runs/:runId route param
    status: str


@app.post("/runs", response_model=RunAccepted, status_code=201)
async def post_runs(req: RunRequest) -> RunAccepted:
    container = get_container()
    # Halt-certification gate (spec US-13) lands fully in slice 18; the hook is here.
    try:
        sealed = SealedSpec.from_yaml(req.spec_yaml)
    except Exception as exc:  # bad spec is a typed 422 to the caller, not a crash
        raise HTTPException(status_code=422, detail=f"Invalid sealed spec: {exc}") from exc

    target_spec = TargetSpec(target_kind=req.target_kind, shape=req.shape, artifact_ref="")
    budget = AttackBudget(max_rounds=req.budget_rounds, max_dollars=req.budget_dollars)
    run_id = await create_run(target_spec, sealed, budget)

    task = asyncio.create_task(run_loop(run_id, container))
    _background.add(task)
    task.add_done_callback(_background.discard)

    return RunAccepted(runId=str(run_id), status=RunStatus.pending)


@app.get("/health")
async def get_health() -> dict[str, object]:
    statuses = await get_container().sink.run_health()
    return {
        name: {"status": s.status, "detail": dict(s.detail), "error": s.error}
        for name, s in statuses.items()
    }


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, object]:
    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return {
        "runId": run.id,
        "status": run.status,
        "target_kind": run.target_kind,
        "shape": run.shape,
        "budget_rounds": run.budget_rounds,
        "budget_dollars": run.budget_dollars,
        "dollars_spent": run.dollars_spent,
        "halted": run.halted,
        "white_box_recall": run.white_box_recall,
        "error": run.error,
    }


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> EventSourceResponse:
    sink = get_container().sink

    async def event_source() -> AsyncIterator[dict[str, str]]:
        async for event in sink.subscribe(RunId(run_id)):
            yield {"event": str(event["kind"]), "data": json.dumps(event["payload"])}

    return EventSourceResponse(event_source())


@app.get("/metrics")
async def get_metrics(run_id: str | None = None) -> dict[str, object]:
    """Honest headline tiles (spec US-10). None tiles render 'Not yet measured'."""
    async with session_scope() as session:
        return await compute_metrics(session, run_id)


@app.get("/runs/{run_id}/verdicts")
async def list_verdicts(run_id: str) -> list[dict[str, object]]:
    async with session_scope() as session:
        rows = (
            await session.execute(select(VerdictRow).where(VerdictRow.run_id == run_id))
        ).scalars().all()
    return [
        {
            "verdictId": v.id, "attackId": v.attack_id, "outcome": v.outcome,
            "tally": v.tally, "threshold": v.threshold,
            "fired": [vote["oracle"] for vote in v.votes if vote.get("fired")],
        }
        for v in rows
    ]


@app.get("/verdicts/{verdict_id}")
async def get_verdict(verdict_id: str) -> dict[str, object]:
    """Full verdict detail (spec US-3/US-4): producer output + five oracle cards."""
    async with session_scope() as session:
        v = (
            await session.execute(select(VerdictRow).where(VerdictRow.id == verdict_id))
        ).scalar_one_or_none()
        if v is None:
            raise HTTPException(status_code=404, detail="verdict not found")
        attack = (
            await session.execute(select(AttackRow).where(AttackRow.id == v.attack_id))
        ).scalar_one_or_none()
    return {
        "verdictId": v.id, "runId": v.run_id, "attackId": v.attack_id,
        "outcome": v.outcome, "tally": v.tally, "threshold": v.threshold,
        "producer_output": v.producer_output,
        "votes": v.votes,                       # five oracle cards: obligation, observation, reason
        "audit_trace": v.audit_trace,
        "seed": v.seed, "dollars": v.dollars_spent,
        "attack": None if attack is None else {
            "tactic": attack.tactic, "payload": attack.payload,
            "white_box": attack.white_box, "rationale": attack.rationale,
        },
    }


@app.get("/corpus")
async def get_corpus(run_id: str | None = None) -> Response:
    """Seeded-hack corpus as JSONL (spec US-11)."""
    async with session_scope() as session:
        rows = await export_corpus(session, run_id)
    body = "\n".join(json.dumps(row) for row in rows)
    return Response(content=body, media_type="application/x-ndjson",
                    headers={"X-Row-Count": str(len(rows))})


@app.get("/catalog")
async def get_catalog(run_id: str | None = None) -> list[dict[str, object]]:
    """Strategy catalog: successful (undetected) tactics, grouped (spec US-6)."""
    async with session_scope() as session:
        rows = await export_corpus(session, run_id)
    counts: dict[str, int] = {}
    meta: dict[str, dict[str, object]] = {}
    for row in rows:
        tactic = str(row["tactic"])
        counts[tactic] = counts.get(tactic, 0) + 1
        if tactic not in meta:
            meta[tactic] = {"tactic": tactic, "target_type": row["target_type"],
                            "first_run": row["run_id"], "white_box": False}
        if row["white_box"]:
            meta[tactic]["white_box"] = True
    return [{**meta[t], "reuse_count": counts[t]} for t in meta]


@app.get("/reports/{run_id}")
async def get_report(run_id: str) -> Response:
    """SR 11-7 model risk report as Markdown (spec US-12)."""
    async with session_scope() as session:
        try:
            markdown = await sr_11_7_markdown(session, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=markdown, media_type="text/markdown")
