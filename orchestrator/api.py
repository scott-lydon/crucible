"""FastAPI application.

Slice 0 ships the three endpoints the foundation needs: POST /runs (persist a
run, return its id), GET /health (liveness plus database reachability), and
GET /runs/:runId/stream (SSE). Raw input is parsed into typed domain objects
at this boundary and never re-validated downstream (coding-practices.md
"parse, do not validate"). This is one of the only two sanctioned catch sites
(the FastAPI boundary); everywhere else exceptions ride up.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from shared.persistence import get_session, ping
from shared.persistence.models import Run
from shared.telemetry import configure_logging, get_logger
from shared.types import (
    AttackBudget,
    DomainValidationError,
    Money,
    RunId,
    RunStatus,
    SealedSpec,
    TargetSpec,
    TargetType,
)

log = get_logger("orchestrator.api")

# FastAPI dependency alias. The Annotated form keeps the Depends() call out of
# the parameter default, which is both the recommended FastAPI style and ruff
# B008 clean.
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class BudgetRequest(BaseModel):
    """The red-search budget from the POST /runs body."""

    max_attempts: int
    max_dollars: float


class RunRequest(BaseModel):
    """The POST /runs request body."""

    target_type: str
    artifact_ref: str
    spec: dict[str, Any]
    budget: BudgetRequest


class RunCreated(BaseModel):
    """The POST /runs response body."""

    run_id: str
    status: str


class HealthResponse(BaseModel):
    """The GET /health response body."""

    status: str
    database: str


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


app = FastAPI(title="Crucible", version="0.1.0", lifespan=lifespan)


@app.exception_handler(DomainValidationError)
async def _domain_validation_handler(_: Request, exc: Exception) -> JSONResponse:
    """Turn a boundary parse failure into a 422 with the curated message.

    DomainValidationError messages are written for the operator and carry no
    SQL or file paths, so returning the message tells them exactly what to fix.
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def _parse_target_type(raw: str) -> TargetType:
    """Parse the request's target_type, naming the valid set on failure."""
    try:
        return TargetType(raw)
    except ValueError as exc:
        valid = ", ".join(t.value for t in TargetType)
        raise DomainValidationError(
            f"Unknown target_type {raw!r}; expected one of: {valid}."
        ) from exc


@app.post("/runs", status_code=201)
async def create_run(req: RunRequest, session: SessionDep) -> RunCreated:
    """Persist a new run as pending and return its id.

    The loop that drives rounds against a registered target lands in slice 1;
    slice 0 deliberately does not fake any rounds.
    """
    spec = SealedSpec.from_payload(req.spec)
    target = TargetSpec(
        target_type=_parse_target_type(req.target_type),
        artifact_ref=req.artifact_ref,
    )
    budget = AttackBudget(
        max_attempts=req.budget.max_attempts,
        max_dollars=Money.of(req.budget.max_dollars),
    )
    run_id = RunId.new()
    run = Run(
        id=run_id.value,
        status=RunStatus.PENDING.value,
        target_type=target.target_type.value,
        artifact_ref=target.artifact_ref,
        spec_title=spec.title,
        spec_json=spec.as_json(),
        budget_max_attempts=budget.max_attempts,
        budget_max_dollars=budget.max_dollars.dollars,
        seed=uuid.uuid4().hex,
    )
    session.add(run)
    await session.commit()
    log.info("run_created", run_id=run_id.value, target_type=target.target_type.value)
    return RunCreated(run_id=run_id.value, status=RunStatus.PENDING.value)


@app.get("/health")
async def health(session: SessionDep) -> HealthResponse:
    """Liveness plus a real database round trip, so /health is never a lie."""
    await ping(session)
    return HealthResponse(status="ok", database="connected")


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, session: SessionDep) -> EventSourceResponse:
    """Stream a run's events over SSE.

    Slice 0 emits the run's current status as a single event. The live
    per-row SSE backend lands in the Measure slice (15).
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    status = run.status

    async def event_gen() -> AsyncIterator[dict[str, str]]:
        yield {
            "event": "run_status",
            "data": json.dumps({"run_id": run_id, "status": status}),
        }

    return EventSourceResponse(event_gen())
