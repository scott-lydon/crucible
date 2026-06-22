"""FastAPI surface. Slice 0: ``POST /runs``, ``GET /health``, ``GET /runs/{id}`` and
the SSE stream. The dashboard (deferred) is a thin client over these endpoints; the
API is the product surface every other slice verifies through."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from orchestrator.loop import create_run, run_loop
from orchestrator.wiring import get_container
from shared.persistence.db import session_scope
from shared.persistence.models import Run
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
