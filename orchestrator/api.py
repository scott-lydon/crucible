"""FastAPI application.

Slice 0 ships the three endpoints the foundation needs: POST /runs (persist a
run, return its id), GET /health (liveness plus database reachability), and
GET /runs/:runId/stream (SSE). Raw input is parsed into typed domain objects
at this boundary and never re-validated downstream (coding-practices.md
"parse, do not validate"). This is one of the only two sanctioned catch sites
(the FastAPI boundary); everywhere else exceptions ride up.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from modules.measure import (
    CorpusExporter,
    HaltRule,
    MetricsAggregator,
    ReportRunNotFoundError,
    RiskReport,
)
from modules.red import StrategyCatalog
from orchestrator.errors import NoOracleRegisteredError, NoTargetRegisteredError
from orchestrator.loop import Loop
from orchestrator.wiring import get_registry
from shared.persistence import get_session, get_sessionmaker, ping
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import (
    BluePatch as BluePatchRow,
)
from shared.persistence.models import (
    DifferentialRun,
    FuzzFinding,
    HoldoutRun,
    JudgeVote,
    ModelVersion,
    Run,
)
from shared.persistence.models import Verdict as VerdictRow
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

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FRONTEND_DIR = _REPO_ROOT / "frontend"

# Strong references to in-flight background run tasks, so the event loop does not
# garbage-collect a run mid-flight (asyncio holds only weak references to tasks).
_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


def _catalog_jsonl_path() -> Path:
    """The append-only strategy-catalog discovery log on disk (US-6)."""
    return _REPO_ROOT / "data" / "strategy_catalog.jsonl"

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
    halt = await HaltRule(session=session).current()
    if halt.halted:
        raise HTTPException(status_code=409, detail=halt.as_json())
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


@app.get("/health/targets/{target_type}")
async def target_health(target_type: str) -> dict[str, Any]:
    """Run one target's self-test (US-8).

    Returns 404 for an unknown target type or one with no registered adapter,
    so a typo is distinguishable from a target that is down.
    """
    try:
        parsed = TargetType(target_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="unknown target type") from exc
    try:
        target = get_registry().target_for(parsed)
    except NoTargetRegisteredError as exc:
        raise HTTPException(status_code=404, detail="target not registered") from exc
    probe = await target.self_test()
    return {"target_type": target_type, "status": probe.status.value, "detail": probe.detail}


@app.get("/catalog")
async def catalog(session: SessionDep) -> list[dict[str, Any]]:
    """The strategy catalog: every recorded successful evasion tactic (US-6).

    Most-reused first. Each row carries the tactic, target-type, first-discovered
    run, reuse count, average dollars-to-succeed, the payload fragment, and the
    discovery audit trace, so the catalog is browsable institutional memory.
    """
    cat = StrategyCatalog(session=session, jsonl_path=_catalog_jsonl_path())
    return [entry.as_json() for entry in await cat.entries()]


@app.get("/metrics")
async def metrics(session: SessionDep) -> dict[str, Any]:
    """Headline catch-rate metrics: black-box and white-box side by side (US-14).

    Each is verifier recall (caught / judged) for that red pass, measured from
    real verdicts only; the gap between them is the report card, how much catch
    rate is borrowed from attacker ignorance. A box with zero judged attacks
    reports a null rate the dashboard renders as "Not yet measured" (US-10).
    """
    return (await MetricsAggregator(session=session).catch_rates()).as_json()


async def _run_loop_background(run_id: str) -> None:
    """Drive one run's loop on its own session (the POST /runs/:id/start task).

    Opens a fresh session (the request's is closed once the route returns 202),
    runs the wired Loop, and on failure marks the run failed rather than leaving
    it stuck RUNNING, so the dashboard reflects a crash honestly.
    """
    try:
        async with get_sessionmaker()() as session:
            await Loop(session=session, registry=get_registry()).run(run_id)
    except Exception as exc:  # the run is long and out-of-band; record, never swallow
        log.error("run_loop_failed", run_id=run_id, error=f"{type(exc).__name__}: {exc}")
        async with get_sessionmaker()() as session:
            run = await session.get(Run, run_id)
            if run is not None:
                run.status = RunStatus.FAILED.value
                await session.commit()


@app.post("/runs/{run_id}/start", status_code=202)
async def start_run(run_id: str, session: SessionDep) -> dict[str, str]:
    """Trigger the loop for a created run in the background (US-1).

    Returns 202 immediately; the loop runs out-of-band (it spends minutes of LLM
    time) and streams rows to the SSE endpoint. 404 for an unknown run, 409 if it
    is already past pending so a run is never double-driven.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status != RunStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"run already {run.status}")
    run.status = RunStatus.RUNNING.value
    await session.commit()
    task = asyncio.create_task(_run_loop_background(run_id))
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return {"run_id": run_id, "status": RunStatus.RUNNING.value}


@app.get("/runs")
async def list_runs(session: SessionDep) -> list[dict[str, Any]]:
    """Every run, newest first, for the Run list (US-2)."""
    rows = (
        (await session.execute(select(Run).order_by(Run.created_at.desc()))).scalars().all()
    )
    return [
        {
            "run_id": r.id,
            "status": r.status,
            "target_type": r.target_type,
            "spec_title": r.spec_title,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/runs/{run_id}")
async def get_run(run_id: str, session: SessionDep) -> dict[str, Any]:
    """One run with its attacks and verdict summaries (US-2)."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    attacks = (
        (await session.execute(select(AttackRow).where(AttackRow.run_id == run_id)))
        .scalars()
        .all()
    )
    verdicts = (
        (await session.execute(select(VerdictRow).where(VerdictRow.run_id == run_id)))
        .scalars()
        .all()
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "target_type": run.target_type,
        "spec_title": run.spec_title,
        "attacks": [
            {
                "attack_id": a.id,
                "tactic": a.tactic,
                "succeeded": a.succeeded,
                "white_box": a.white_box,
                "hybrid": a.hybrid,
                "dollars_spent": str(a.dollars_spent),
            }
            for a in attacks
        ],
        "verdicts": [
            {
                "verdict_id": v.id,
                "attack_id": v.attack_id,
                "passed": v.passed,
                "tally": v.tally,
            }
            for v in verdicts
        ],
    }


@app.get("/runs/{run_id}/verdicts/{verdict_id}")
async def get_verdict(run_id: str, verdict_id: str, session: SessionDep) -> dict[str, Any]:
    """One verdict with its votes and the per-oracle drill-down rows (US-4)."""
    verdict = await session.get(VerdictRow, verdict_id)
    if verdict is None or verdict.run_id != run_id:
        raise HTTPException(status_code=404, detail="verdict not found")
    judge = (
        (await session.execute(select(JudgeVote).where(JudgeVote.verdict_id == verdict_id)))
        .scalars()
        .all()
    )
    fuzz = (
        (await session.execute(select(FuzzFinding).where(FuzzFinding.verdict_id == verdict_id)))
        .scalars()
        .all()
    )
    differential = (
        (
            await session.execute(
                select(DifferentialRun).where(DifferentialRun.verdict_id == verdict_id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "verdict_id": verdict.id,
        "run_id": verdict.run_id,
        "passed": verdict.passed,
        "tally": verdict.tally,
        "votes": verdict.votes,
        "audit_trace": verdict.audit_trace,
        "judge_votes": [
            {"decision": j.decision, "weight": j.weight, "reason": j.reason} for j in judge
        ],
        "fuzz_findings": [
            {"decision": f.decision, "counterexample": f.counterexample} for f in fuzz
        ],
        "differential_runs": [
            {"decision": d.decision, "reason": d.reason} for d in differential
        ],
    }


@app.get("/blue/{patch_id}")
async def get_blue_patch(patch_id: str, session: SessionDep) -> dict[str, Any]:
    """One blue patch with its held-out validation and model version (US-7)."""
    patch = await session.get(BluePatchRow, patch_id)
    if patch is None:
        raise HTTPException(status_code=404, detail="patch not found")
    holdout = (
        (await session.execute(select(HoldoutRun).where(HoldoutRun.patch_id == patch_id)))
        .scalars()
        .all()
    )
    versions = (
        (await session.execute(select(ModelVersion).where(ModelVersion.patch_id == patch_id)))
        .scalars()
        .all()
    )
    return {
        "patch_id": patch.id,
        "target_type": patch.target_type,
        "kind": patch.kind,
        "detail": patch.detail,
        "provenance": patch.provenance,
        "audit_trace": patch.audit_trace,
        "holdout_runs": [
            {
                "holdout_size": h.holdout_size,
                "detection_before": h.detection_before,
                "detection_after": h.detection_after,
                "recovered": h.recovered,
            }
            for h in holdout
        ],
        "model_versions": [
            {"version": m.version, "artifact_ref": m.artifact_ref, "metrics": m.metrics}
            for m in versions
        ],
    }


# The .pdf route is registered before /reports/{run_id} so the literal suffix
# wins; otherwise {run_id} would greedily capture "abc.pdf".
@app.get("/halt")
async def halt(session: SessionDep) -> dict[str, Any]:
    """The certification halt state and the banner text every route shows (US-13).

    Recomputed from the latest white-box recall on each read and persisted, so
    the dashboard banner and the launch guard agree.
    """
    state = await HaltRule(session=session).evaluate()
    await session.commit()
    return state.as_json()


@app.get("/reports/{run_id}.pdf")
async def report_pdf(run_id: str, session: SessionDep) -> Response:
    """The same SR 11-7 report as a downloadable PDF (US-12)."""
    try:
        pdf = await RiskReport(session=session).render_pdf(run_id)
    except ReportRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=crucible-report-{run_id}.pdf"},
    )


@app.get("/reports/{run_id}")
async def report_markdown(run_id: str, session: SessionDep) -> dict[str, Any]:
    """The SR 11-7 report for a run as Markdown, numbers linked to their rows (US-12)."""
    try:
        markdown = await RiskReport(session=session).render_markdown(run_id)
    except ReportRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return {"run_id": run_id, "markdown": markdown}


@app.get("/corpus")
async def corpus(session: SessionDep) -> dict[str, Any]:
    """The successful-attack corpus table plus its exact row count (US-11)."""
    exporter = CorpusExporter(session=session)
    return {"count": await exporter.count(), "rows": await exporter.rows()}


@app.get("/corpus.jsonl")
async def corpus_download() -> StreamingResponse:
    """Download the corpus as JSONL; one line per successful attack (US-11).

    Streams over its own session (the request session closes once the response
    starts) and reads the same query as `/corpus`, so the downloaded row count
    equals the table row count exactly.
    """

    async def generate() -> AsyncIterator[str]:
        async with get_sessionmaker()() as session:
            async for line in CorpusExporter(session=session).stream_jsonl():
                yield line

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=crucible-corpus.jsonl"},
    )


@app.get("/health/oracles/{name}")
async def oracle_health(name: str) -> dict[str, Any]:
    """Run one oracle's self-test (US-8). 404 when no oracle is registered by name."""
    try:
        oracle = get_registry().oracle_for(name)
    except NoOracleRegisteredError as exc:
        raise HTTPException(status_code=404, detail="oracle not registered") from exc
    probe = await oracle.self_test()
    return {"oracle": name, "status": probe.status.value, "detail": probe.detail}


_SSE_POLL_SECONDS = 1.0
_SSE_MAX_TICKS = 600  # ~10 minutes, then the stream closes rather than hang forever


async def _run_events(run_id: str) -> AsyncIterator[dict[str, str]]:
    """Emit each persisted attack and verdict as it appears, then a final status.

    Polls Postgres on a short interval and pushes only rows not yet seen, so the
    ASR chart updates once per attack (US-2). The stream ends when the run reaches
    a terminal status (complete or failed) or the safety tick cap is hit.
    """
    seen_attacks: set[str] = set()
    seen_verdicts: set[str] = set()
    for _ in range(_SSE_MAX_TICKS):
        async with get_sessionmaker()() as session:
            run = await session.get(Run, run_id)
            if run is None:
                yield {"event": "error", "data": json.dumps({"detail": "run not found"})}
                return
            attacks = (
                (await session.execute(select(AttackRow).where(AttackRow.run_id == run_id)))
                .scalars()
                .all()
            )
            verdicts = (
                (await session.execute(select(VerdictRow).where(VerdictRow.run_id == run_id)))
                .scalars()
                .all()
            )
            status = run.status
        for a in attacks:
            if a.id not in seen_attacks:
                seen_attacks.add(a.id)
                yield {
                    "event": "attack",
                    "data": json.dumps(
                        {
                            "attack_id": a.id,
                            "tactic": a.tactic,
                            "succeeded": a.succeeded,
                            "white_box": a.white_box,
                        }
                    ),
                }
        for v in verdicts:
            if v.id not in seen_verdicts:
                seen_verdicts.add(v.id)
                yield {
                    "event": "verdict",
                    "data": json.dumps(
                        {"verdict_id": v.id, "attack_id": v.attack_id, "passed": v.passed}
                    ),
                }
        if status in (RunStatus.COMPLETE.value, RunStatus.FAILED.value):
            yield {"event": "run_status", "data": json.dumps({"run_id": run_id, "status": status})}
            return
        await asyncio.sleep(_SSE_POLL_SECONDS)


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, session: SessionDep) -> EventSourceResponse:
    """Stream a run's attacks and verdicts over SSE as they are persisted (US-2)."""
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return EventSourceResponse(_run_events(run_id))


# The live wiring sidecar is injected into every served design page so the
# canonical .dc.html files stay byte-identical on disk (verbatim UI) while the
# served app fetches live backend data and swaps the stubbed values.
_LIVE_TAG = '<script src="./live.js" defer></script>'


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".md": "text/plain",
    }.get(suffix, "application/octet-stream")


@app.get("/app")
async def app_root() -> RedirectResponse:
    """Route '/' of the dashboard maps to the Run Launcher (frontend/index.html)."""
    return RedirectResponse(url="/app/slice-01-run-launcher.dc.html")


@app.get("/app/{path:path}")
async def app_static(path: str) -> Any:
    """Serve the verbatim design bundle, injecting the live-data sidecar into HTML.

    The on-disk .dc.html stay byte-identical (the design fidelity rule); the live
    wiring rides an injected `<script src=live.js>` and replaces only the stubbed
    data, never the UI markup.
    """
    target = (_FRONTEND_DIR / path).resolve()
    if not str(target).startswith(str(_FRONTEND_DIR.resolve())) or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    if target.suffix.lower() == ".html":
        html = target.read_text(encoding="utf-8")
        if _LIVE_TAG not in html:
            html = (
                html.replace("</body>", f"{_LIVE_TAG}\n</body>", 1)
                if "</body>" in html
                else html + _LIVE_TAG
            )
        return HTMLResponse(content=html)
    return Response(content=target.read_bytes(), media_type=_media_type(target))
