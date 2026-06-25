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
import secrets
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from modules.measure import (
    CorpusExporter,
    HaltRule,
    MetricsAggregator,
    ReportRunNotFoundError,
    RiskReport,
    get_halt_override,
    set_halt_override,
)
from modules.red import StrategyCatalog
from orchestrator.errors import NoOracleRegisteredError, NoTargetRegisteredError
from orchestrator.loop import Loop
from orchestrator.persisting_llm import PersistingLlmClient
from orchestrator.wiring import build_registry, get_registry
from shared.config import get_settings
from shared.types.default_specs import default_spec_payload, default_spec_yaml
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
    LlmCall,
    ModelVersion,
    Run,
    RunOverride,
    Spec,
    WorkspacePolicy,
)
from shared.persistence.models import Verdict as VerdictRow
from shared.sandbox.docker_sandbox import DEFAULT_SANDBOX_IMAGE
from shared.telemetry import configure_logging, get_logger
from shared.types import (
    Attack,
    AttackBudget,
    AttackId,
    AuditTrace,
    DomainValidationError,
    Money,
    RunId,
    RunStatus,
    SealedSpec,
    TargetSpec,
    TargetType,
)
from modules.blue import BlueProposer, BlueStore
from modules.oracles.aggregator import VerdictAggregator, votes_from_json
from shared.llm import (
    KeySource,
    LlmModel,
    ProviderMode,
    clear_active_key,
    get_llm_client,
    key_hint,
    resolve_provider_mode,
    set_active_key,
)
from shared.llm.active_key import get_active_key, get_prefer_api, set_prefer_api
from shared.types import VerdictId

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
    # US-13: when the latest white-box pass is below the red line the orchestrator
    # refuses new launches with a typed 409 — unless the operator has armed the
    # devmode override (a debug route so testing/recording can proceed without
    # weakening the audit banner, which still reports the real recall).
    halt = await HaltRule(session=session).current()
    if halt.halted and not get_halt_override():
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


@app.get("/me")
async def me() -> dict[str, Any]:
    """Caller identity for the dashboard's header chip and audit-trail readout.

    No auth layer ships in slice 19 (the deployed instance has no sign-in), so
    the route returns the honest anonymous state: a display name of
    ``anonymous`` and a null role. The launcher's role chip renders the null
    role as ``no role`` and the audit-trail line as ``no audit identity``, so
    the operator can see that overrides would not be signed to anyone until
    auth lands. Replacing the hardcoded ``m.chen`` / ``admin · root`` stub.
    """
    return {
        "display_name": "anonymous",
        "role": None,
        "audit_log_target": None,
    }


@app.get("/workspace")
async def workspace() -> dict[str, Any]:
    """The active workspace for the dashboard header chip.

    The platform is single-workspace today; the route returns the one workspace
    that exists, with a null monthly ceiling because no workspace-budget table
    has been seeded yet. The launcher renders the null ceiling as ``no ceiling
    set`` rather than a fabricated ``$250.00 mo`` figure.
    """
    return {
        "name": "default",
        "monthly_ceiling_dollars": None,
    }


@app.get("/spend/current-month")
async def spend_current_month(session: SessionDep) -> dict[str, Any]:
    """Sum of LLM dollars spent this calendar month, plus the workspace ceiling.

    The number reads from the real ``llm_calls.dollars_spent`` column, so a
    fresh database reports ``$0.00`` honestly rather than the hardcoded
    ``$61.40 / $250.00 mo`` stub the design bundle shipped with. The ceiling
    field is null until a workspace-budget table is seeded.
    """
    now = datetime.now(tz=UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    stmt = select(func.coalesce(func.sum(LlmCall.dollars_spent), 0)).where(
        LlmCall.created_at >= month_start
    )
    total = await session.scalar(stmt)
    return {
        "spent_dollars": float(total or 0),
        "ceiling_dollars": None,
        "period_start": month_start.isoformat(),
    }


@app.get("/targets/registered")
async def targets_registered() -> list[dict[str, Any]]:
    """Every target adapter wired into the registry, with its real identity.

    The launcher's target-picker reads from this list, so adding a target only
    requires registering it in ``wiring.py``; no design-bundle markup or
    stubbed JSON needs to change. Each row carries the adapter's own
    ``display_name``, ``description``, and ``artifact_ref`` (Protocol fields,
    computed from the real artifact bytes for Shape 1 targets).
    """
    registry = get_registry()
    rows: list[dict[str, Any]] = []
    for target_type, adapter in registry.targets.items():
        rows.append(
            {
                "type": target_type.value,
                "display_name": adapter.display_name,
                "description": adapter.description,
                "artifact_ref": adapter.artifact_ref,
            }
        )
    return rows


@app.get("/targets/{target_type}/default-spec")
async def target_default_spec(target_type: str) -> dict[str, Any]:
    """The canonical sealed spec a launchable target is sealed under by default.

    The browser Run Launcher fetches this so the spec it seals and shows is the
    backend's single source of truth, never a value hardcoded in the frontend.
    Returns the ``SealedSpec.from_payload``-shaped ``spec`` plus a ``yaml``
    rendering for the sealed-spec panel. 422 (via the domain handler) names the
    launchable set when the target has no default spec.
    """
    parsed = _parse_target_type(target_type)
    return {
        "target_type": parsed.value,
        "spec": default_spec_payload(parsed),
        "yaml": default_spec_yaml(parsed),
    }


@app.get("/oracles/registered")
async def oracles_registered() -> dict[str, Any]:
    """Every oracle wired into the registry, with its weight and pass threshold.

    The launcher's right-rail summary reads the oracle count, the judge weight,
    and the pass threshold from this route, so the ``one of N votes`` phrase is
    computed from the real weights instead of the hardcoded ``one of five``
    that contradicts the actual aggregator (US-4). Each oracle carries the
    ``protocol_description`` it would disclose to the white-box red pass.
    """
    registry = get_registry()
    oracles: list[dict[str, Any]] = [
        {
            "name": oracle.name,
            "weight": float(oracle.weight),
            "protocol_description": oracle.protocol_description,
        }
        for oracle in registry.oracles
    ]
    total_weight = sum(float(item["weight"]) for item in oracles)
    judge: dict[str, Any] | None = next(
        (item for item in oracles if "judge" in str(item["name"]).lower()),
        None,
    )
    judge_share_text = (
        f"{judge['weight']} of {total_weight} votes"
        if judge is not None and total_weight > 0
        else "no judge weighted"
    )
    return {
        "oracles": oracles,
        "total_weight": total_weight,
        "pass_threshold": registry.aggregator.pass_threshold,
        "judge_share_text": judge_share_text,
    }


@app.get("/estimate")
async def estimate(
    target_type: str,
    rounds: int,
    session: SessionDep,
) -> dict[str, Any]:
    """Estimated cost-per-round and run range, from real prior runs.

    The estimate averages ``attacks.dollars_spent`` across every prior attack
    against this target type, and reports a low/high band derived from the
    standard deviation (a one-sigma window scaled by ``sqrt(rounds)``, since
    independent rounds combine variance). When no prior runs exist the route
    returns nulls, which the launcher renders as ``not yet measured`` so a
    fresh deployment never shows a fabricated ``$0.52 per round`` estimate.
    """
    if rounds <= 0:
        raise HTTPException(status_code=422, detail="rounds must be positive")
    avg_stmt = (
        select(func.avg(AttackRow.dollars_spent))
        .join(Run, AttackRow.run_id == Run.id)
        .where(Run.target_type == target_type)
    )
    avg_value = await session.scalar(avg_stmt)
    cost_per_round = float(avg_value) if avg_value is not None else None

    count_stmt = (
        select(func.count(AttackRow.id))
        .join(Run, AttackRow.run_id == Run.id)
        .where(Run.target_type == target_type)
    )
    sample = int(await session.scalar(count_stmt) or 0)

    if cost_per_round is None or sample == 0:
        return {
            "target_type": target_type,
            "rounds": rounds,
            "cost_per_round_dollars": None,
            "low_dollars": None,
            "high_dollars": None,
            "sample_attacks": sample,
        }

    stddev_stmt = (
        select(func.stddev_pop(AttackRow.dollars_spent))
        .join(Run, AttackRow.run_id == Run.id)
        .where(Run.target_type == target_type)
    )
    stddev = float(await session.scalar(stddev_stmt) or 0.0)
    total = cost_per_round * rounds
    spread = stddev * (rounds ** 0.5)
    return {
        "target_type": target_type,
        "rounds": rounds,
        "cost_per_round_dollars": cost_per_round,
        "low_dollars": max(0.0, total - spread),
        "high_dollars": total + spread,
        "sample_attacks": sample,
    }


@app.get("/sandbox/image")
async def sandbox_image() -> dict[str, Any]:
    """The actual Docker image the producer sandbox would launch.

    The launcher's sandbox panel reads the image string from here rather than
    the hardcoded ``crucible/sandbox:v1.4.2`` the design bundle shipped with,
    so an image change in ``shared/sandbox/docker_sandbox.py`` shows up in the
    dashboard the moment it lands.
    """
    return {
        "image": DEFAULT_SANDBOX_IMAGE,
        "egress_blocked": True,
        "network": "sealed (egress deny)",
    }


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
            # Wire a per-run registry whose LLM client records every call to
            # llm_calls (run_id, prompt, response, tokens, cost) so the trace-card
            # Inspect view (US-2) and the spend column (US-10) read real data.
            registry = build_registry(
                llm=PersistingLlmClient(base=get_llm_client(), run_id=run_id)
            )
            await Loop(session=session, registry=registry).run(run_id)
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


@app.get("/runs/{run_id}/llm_calls")
async def run_llm_calls(run_id: str, session: SessionDep) -> list[dict[str, Any]]:
    """Every recorded LLM call for a run, for the trace-card Inspect view (US-2).

    Real prompt, raw response, parsed output, token counts, model and dollar cost
    per call, oldest first. Empty list when the run made no recorded calls.
    """
    rows = (
        (
            await session.execute(
                select(LlmCall)
                .where(LlmCall.run_id == run_id)
                .order_by(LlmCall.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": c.id,
            "pillar": c.pillar,
            "model": c.model,
            "prompt": c.prompt,
            "raw_response": c.raw_response,
            "parsed_output": c.parsed_output,
            "tokens_in": c.tokens_in,
            "tokens_out": c.tokens_out,
            "dollars_spent": float(c.dollars_spent),
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
    ]


@app.post("/runs/{run_id}/verdicts/{verdict_id}/replay")
async def replay_verdict(run_id: str, verdict_id: str, session: SessionDep) -> dict[str, Any]:
    """Deterministically replay a verdict from its captured votes (US-5).

    Re-derives the tally and pass/caught decision from the stored vote rows via
    the same VerdictAggregator the original run used, then diffs the replay
    against the persisted result. A clean replay proves the verdict is
    reproducible from its audit row; any divergence is surfaced as a
    non-determinism incident (it never papers over a mismatch).
    """
    verdict = await session.get(VerdictRow, verdict_id)
    if verdict is None or verdict.run_id != run_id:
        raise HTTPException(status_code=404, detail="verdict not found")
    votes = votes_from_json(verdict.votes or [])
    aggregator = VerdictAggregator()
    replayed = aggregator.aggregate(
        votes,
        run_id=RunId(run_id),
        attack_id=AttackId(verdict.attack_id) if verdict.attack_id else None,
        verdict_id=VerdictId(verdict_id),
    )
    diff: list[str] = []
    if abs(float(replayed.tally) - float(verdict.tally)) > 1e-9:
        diff.append(f"tally: original {verdict.tally} != replay {replayed.tally}")
    if bool(replayed.passed) != bool(verdict.passed):
        diff.append(f"passed: original {verdict.passed} != replay {replayed.passed}")
    return {
        "verdict_id": verdict_id,
        "run_id": run_id,
        "deterministic": not diff,
        "original": {"tally": verdict.tally, "passed": verdict.passed},
        "replay": {"tally": replayed.tally, "passed": replayed.passed},
        "votes": aggregator.votes_as_json(replayed.votes),
        "diff": diff,
    }


@app.post("/runs/{run_id}/blue", status_code=201)
async def trigger_blue(run_id: str, session: SessionDep) -> dict[str, str]:
    """Run the blue hardening loop for a run and persist a patch (US-7).

    Reads the run's undetected attacks (falls back to all attacks), proposes a
    hardening patch via the blue proposer, and persists it so
    GET /blue/{patch_id} can render the review. This is the operator-facing
    trigger the blue-patch view links to; previously no route created a patch,
    so the view could never show real data.
    """
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    rows = (
        (await session.execute(select(AttackRow).where(AttackRow.run_id == run_id)))
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=409, detail="run has no attacks to harden from; run it first"
        )

    def _value(r: AttackRow) -> Attack:
        return Attack(
            attack_id=AttackId(r.id),
            run_id=RunId(r.run_id),
            tactic=r.tactic,
            payload=r.payload or {},
            succeeded=r.succeeded,
            white_box=r.white_box,
            hybrid=r.hybrid,
            dollars_spent=Money.zero(),
            audit=AuditTrace(summary="from run attack", steps=()),
        )

    undetected = [_value(r) for r in rows if r.succeeded]
    slice_attacks = undetected or [_value(r) for r in rows]
    patch = await BlueProposer(llm=get_llm_client()).propose_patch(
        TargetType(run.target_type), slice_attacks
    )
    await BlueStore(session=session).save_patch(patch)
    await session.commit()
    log.info(
        "blue_patch_created",
        run_id=run_id,
        patch_id=patch.patch_id.value,
        kind=patch.kind,
        from_undetected=len(undetected),
    )
    return {"patch_id": patch.patch_id.value, "kind": patch.kind}


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
    body = state.as_json()
    body["override"] = get_halt_override()
    return body


class HaltOverrideRequest(BaseModel):
    """The POST /halt/override body: the devmode launch-guard bypass toggle."""

    enabled: bool


@app.post("/halt/override")
async def halt_override(req: HaltOverrideRequest, request: Request) -> dict[str, Any]:
    """Devmode bypass of the certification halt launch guard (US-13 debug route).

    Admin-gated. When enabled, create_run launches even while halted, so the
    operator can drive manual tests/recordings into states the halted happy path
    cannot reach. The audit banner still reports the real recall; only the launch
    refusal is bypassed. Defaults off, so the spec'd 409 holds by default.
    """
    token = request.cookies.get(_ADMIN_COOKIE)
    if token not in _ADMIN_SESSIONS:
        raise HTTPException(status_code=401, detail="admin session required")
    set_halt_override(req.enabled)
    return {"ok": True, "halt_override": get_halt_override()}


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


@app.get("/policy")
async def policy(session: SessionDep) -> dict[str, Any]:
    """The workspace's operative governance policy (slice-15, C12).

    Returns the real config-derived halt policy (certification halts when
    white-box recall falls below the threshold) plus any custom policy stored in
    the workspace_policy table. A fresh deployment with no stored policy still
    returns the operative halt policy, so the page renders a real rule rather
    than the design bundle's hardcoded MRG-* list.
    """
    stored = await session.get(WorkspacePolicy, "global")
    threshold = get_settings().halt_recall_threshold
    return {
        "workspace": "default",
        "halt_recall_threshold": threshold,
        "operative_policy": (
            f"certification halts when white-box recall < {threshold:.2f}"
        ),
        "custom_policy_yaml": stored.policy_yaml if stored is not None else None,
        "updated_at": stored.updated_at.isoformat() if stored is not None else None,
    }


# ====================================================================
# LLM provider admin (deploy-time Anthropic API fallback to the CLI)
# ====================================================================
# SECURITY NOTE: the admin credentials below are trivial hardcoded values
# ("admin" / "pass"), per explicit operator request for this single-operator
# demo. On a public deploy anyone who guesses them can enable the server's
# project key and spend the operator's Anthropic credit. The mitigation in
# scope is that the project-key path only works if the operator has set
# ANTHROPIC_API_KEY on the server (it is never in the repo), and the user-key
# path spends the visitor's own key, not the project's. Do not treat admin/pass
# as real authentication.
_ADMIN_USERNAME = "admin"
_ADMIN_PASSWORD = "pass"
_ADMIN_COOKIE = "crucible_admin"

# In-memory set of valid admin session tokens. Cleared on process restart, which
# is acceptable for the single-operator demo (the operator logs in again). An
# opaque random token in an HttpOnly cookie is the smallest secure-enough check:
# the token is never guessable and never readable by page JavaScript.
_ADMIN_SESSIONS: set[str] = set()


class AdminLoginRequest(BaseModel):
    """The POST /admin/login body."""

    username: str
    password: str


class LlmKeyRequest(BaseModel):
    """The POST /llm-key body: a visitor-supplied Anthropic API key."""

    api_key: str


class PreferApiRequest(BaseModel):
    """The POST /llm-provider/prefer body: the run-provider preference toggle."""

    prefer_api: bool


@app.post("/admin/login")
async def admin_login(req: AdminLoginRequest, response: Response) -> dict[str, Any]:
    """Authenticate the single operator and enable the server's project key.

    On correct credentials this issues an opaque HttpOnly session cookie and, if
    ANTHROPIC_API_KEY is configured on the server, installs it as the active
    fallback key so a deployed run (no `claude` CLI) can call the real API. If
    the env var is unset the login still succeeds but the response says the
    project key is not configured, rather than fabricating a key.
    """
    if not (
        secrets.compare_digest(req.username, _ADMIN_USERNAME)
        and secrets.compare_digest(req.password, _ADMIN_PASSWORD)
    ):
        raise HTTPException(status_code=401, detail="invalid admin credentials")

    token = secrets.token_urlsafe(32)
    _ADMIN_SESSIONS.add(token)
    response.set_cookie(
        key=_ADMIN_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        path="/",
    )

    project_key = get_settings().anthropic_api_key
    if project_key:
        set_active_key(project_key, KeySource.PROJECT)
        return {
            "ok": True,
            "project_key_configured": True,
            "message": "Admin session started. Project key enabled as the LLM fallback.",
        }
    return {
        "ok": True,
        "project_key_configured": False,
        "message": (
            "Admin session started, but ANTHROPIC_API_KEY is not configured on "
            "the server, so the project key cannot be enabled. Set it on the "
            "server, or paste your own key below."
        ),
    }


@app.post("/llm-key")
async def set_llm_key(req: LlmKeyRequest) -> dict[str, Any]:
    """Store a visitor-supplied Anthropic key as the active fallback (no admin).

    Used on the deployed instance when the operator has not configured a project
    key: the visitor spends their own key. The key is held in the process-level
    store only, never persisted and never echoed back; the response returns only
    a last-four hint.
    """
    candidate = req.api_key.strip()
    if not candidate:
        raise HTTPException(status_code=422, detail="api_key must not be empty")
    set_active_key(candidate, KeySource.USER)
    return {"ok": True, "source": KeySource.USER.value, "key_hint": key_hint(candidate)}


@app.post("/llm-key/clear")
async def clear_llm_key() -> dict[str, Any]:
    """Forget any stored fallback key, reverting the deployed instance to none."""
    clear_active_key()
    return {"ok": True}


@app.post("/llm-provider/prefer")
async def set_provider_preference(req: PreferApiRequest) -> dict[str, Any]:
    """Toggle whether runs prefer the Anthropic API over the local `claude` CLI.

    SECURITY NOTE: turning this on routes every run through the active key, which
    spends that key owner's Anthropic credit per call (the project key after an
    admin login, or the visitor's own pasted key). It defaults OFF and only
    changes the selection when a key is already active; with no key the resolver
    falls back to the CLI honestly. Returns the resulting resolved mode so the UI
    reflects what runs will actually use (single-sourced with /llm-provider).
    """
    set_prefer_api(req.prefer_api)
    return {"ok": True, "prefer_api": get_prefer_api(), "mode": resolve_provider_mode().value}


@app.get("/llm-provider")
async def llm_provider() -> dict[str, Any]:
    """The active LLM provider state for the central indicator and admin panel.

    Computed by the same resolution `get_llm_client` uses, so the chip can never
    claim a provider the run loop would not pick. Never returns the full key,
    only a last-four hint when a key is active. `prefer_api` reflects the
    run-provider toggle so the admin panel can show its state.
    """
    mode = resolve_provider_mode()
    active = get_active_key()
    labels = {
        ProviderMode.CLI: "local CLI",
        ProviderMode.PROJECT_KEY: "project key",
        ProviderMode.USER_KEY: "your key",
        ProviderMode.MOCK: "mock",
        ProviderMode.NONE: "none",
    }
    return {
        "mode": mode.value,
        "model_family": LlmModel.OPUS.value,
        "key_hint": key_hint(active.value) if active is not None else None,
        "source_label": labels[mode],
        "prefer_api": get_prefer_api(),
    }


@app.get("/admin/overrides")
async def admin_overrides(session: SessionDep) -> list[dict[str, Any]]:
    """The admin override audit log, newest first (slice-12, C9).

    Append-only record of every override the admin debug panel applied. Empty on
    a fresh deployment, which the panel renders as "no overrides recorded"
    instead of the design bundle's hardcoded audit rows.
    """
    rows = (
        (await session.execute(select(RunOverride).order_by(RunOverride.created_at.desc())))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "field": r.field,
            "value": r.value,
            "actor": r.actor,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/specs/history")
async def specs_history(session: SessionDep) -> list[dict[str, Any]]:
    """Every sealed spec, newest first: the versioned spec history (slice 16).

    Reads the real `specs` table the resolver writes; a fresh deployment returns
    an empty list the page renders as "no specs sealed yet" rather than the
    hardcoded version rows the design bundle shipped with. Each row carries the
    spec id, its title and obligation count (read from the stored `as_json`
    form), and when it was sealed.
    """
    rows = (
        (await session.execute(select(Spec).order_by(Spec.created_at.desc())))
        .scalars()
        .all()
    )
    history: list[dict[str, Any]] = []
    for r in rows:
        spec_json = r.spec_json if isinstance(r.spec_json, dict) else {}
        obligations = spec_json.get("obligations", [])
        history.append(
            {
                "spec_id": r.id,
                "title": spec_json.get("title"),
                "obligations": len(obligations) if isinstance(obligations, list) else 0,
                "created_at": r.created_at.isoformat(),
            }
        )
    return history


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


@app.get("/")
async def root() -> RedirectResponse:
    """Root of the deployed service redirects to the dashboard's Run Launcher.

    A bare GET / returning 404 makes the URL look broken to anyone who lands on
    it without a path, so the root hops to /app, which itself hops to the Run
    Launcher page (`frontend/slice-01-run-launcher.dc.html`).
    """
    return RedirectResponse(url="/app")


@app.get("/app")
async def app_root() -> RedirectResponse:
    """Route '/' of the dashboard maps to the Run Launcher (frontend/index.html)."""
    return RedirectResponse(url="/app/Run%20Launcher.dc.html")


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
        # New React-harness design self-wires data in each slice's inline script;
        # the old data-live sidecar (live.js) no longer applies.
        if False and _LIVE_TAG not in html:
            html = (
                html.replace("</body>", f"{_LIVE_TAG}\n</body>", 1)
                if "</body>" in html
                else html + _LIVE_TAG
            )
        return HTMLResponse(content=html)
    return Response(content=target.read_bytes(), media_type=_media_type(target))
