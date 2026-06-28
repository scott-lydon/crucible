"""FastAPI surface. Slice 0: ``POST /runs``, ``GET /health``, ``GET /runs/{id}`` and
the SSE stream. The dashboard (deferred) is a thin client over these endpoints; the
API is the product surface every other slice verifies through."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from modules.blue.errors import HoldoutContamination
from modules.blue.holdout_validator import HoldoutValidator
from modules.measure.admin import debug_summary, leaderboard
from modules.measure.budget import budget_status, global_spend
from modules.measure.corpus import export_corpus
from modules.measure.halt import get_halt_override, halt_state, set_halt_override
from modules.measure.metrics import compute_metrics
from modules.measure.report import sr_11_7_markdown, sr_11_7_pdf
from modules.measure.trust import compute_trust
from modules.oracles.aggregator import vote_as_json, votes_from_json
from modules.oracles.protocol import oracle_protocols
from modules.red.catalog import build_catalog, read_discovery_log
from modules.red.white_box import compose_white_box_brief
from modules.targets.agent import (
    HttpEndpointConfig,
    demo_agent,
    validate_agent_config,
    validate_http_endpoint,
)
from orchestrator.errors import NoTargetRegisteredError
from orchestrator.loop import create_run, run_coevolution, run_loop
from orchestrator.wiring import build_container, get_container, set_container
from shared.config import load_settings
from shared.persistence.db import session_scope
from shared.persistence.models import (
    AgentConfigRow,
    AttackRow,
    CoevolutionRoundRow,
    LLMCallRow,
    Run,
    SpecRow,
    VerdictRow,
)
from shared.persistence.resolver import resolve_spec
from shared.persistence.store import (
    coevolution_series,
    save_agent_config,
    save_coevolution_round,
)
from shared.telemetry.log import configure_logging
from shared.types.agent import AgentConfig
from shared.types.core import Attack, AttackBudget, TargetSpec
from shared.types.enums import Pillar, RunStatus, Shape
from shared.types.errors import CrucibleError
from shared.types.ids import AttackId, RunId, new_id
from shared.types.sealed_spec import HumanSpec, SealedSpec

# Background loop tasks, kept referenced so they are not garbage-collected mid-run.
_background: set[asyncio.Task[None]] = set()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(json_output=False)
    yield


app = FastAPI(title="Crucible", version="0.1.0", lifespan=_lifespan)


@app.exception_handler(CrucibleError)
async def _crucible_error_handler(_request: Any, exc: CrucibleError) -> JSONResponse:
    """A typed wiring error (no target / no oracle registered) is the caller's mistake,
    not a server crash: surface its self-describing message as a 422 so the operator sees
    "Registered target types: ..." instead of "Internal server error" (PR3 port A2)."""
    return JSONResponse(status_code=422, content={"detail": str(exc)})


class HumanSpecModel(BaseModel):
    """The plain-English spec for a Shape-2 agent run; compiled server-side into
    obligations (cr-a2/cr-a4). The operator never writes sealed-spec YAML for an agent."""

    task: str
    failure_conditions: list[str] = Field(default_factory=list)
    hidden_tests: list[str] = Field(default_factory=list)


class AgentSpecModel(BaseModel):
    """A bring-your-own agent: a vendor model + system prompt the run will red-team
    (cr-e2). When absent, an agent run targets the built-in demo agent."""

    name: str = "byo-agent"
    model: str
    system_prompt: str
    params: dict[str, object] = Field(default_factory=dict)


class HttpEndpointModel(BaseModel):
    """A bring-your-own agent that already runs behind an HTTP endpoint (cr-ui4). Crucible
    red-teams it as a black box: it POSTs the crafted input and reads the reply from a
    configurable JSON field."""

    name: str = "byo-http"
    endpoint: str
    input_field: str = "input"
    output_field: str = "output"
    method: str = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 60.0


class RunRequest(BaseModel):
    target_kind: str = Field(examples=["fraud", "agent"])
    shape: str = Field(examples=["shape1_ml", "shape2_agent"])
    # Provide exactly one: sealed-spec YAML (Shape 1) OR a plain-English human_spec
    # (Shape 2 agent, compiled by the wired spec compiler).
    spec_yaml: str | None = None
    human_spec: HumanSpecModel | None = None
    # Agent target selection (Shape 2): a BYO agent, a built-in demo by name, or a BYO
    # HTTP endpoint that Crucible red-teams as a black box.
    agent: AgentSpecModel | None = None
    demo_agent: str | None = None
    http_endpoint: HttpEndpointModel | None = None
    budget_rounds: int = Field(default=5, ge=1, le=200)
    budget_dollars: float = Field(default=2.0, ge=0.0)
    # "redteam" = red + white-box self-test; "coevolution" = red->verify->blue->red rounds.
    mode: str = Field(default="redteam", examples=["redteam", "coevolution"])
    coevo_rounds: int = Field(default=3, ge=1, le=20)
    attacks_per_round: int = Field(default=3, ge=1, le=20)


class RunAccepted(BaseModel):
    runId: str  # noqa: N815 — matches the dashboard's /runs/:runId route param
    status: str


@app.post("/runs", response_model=RunAccepted, status_code=201)
async def post_runs(req: RunRequest) -> RunAccepted:
    container = get_container()
    # Fail loud at the boundary (PR3 port A2): an unregistered target_kind is rejected here
    # with the registered-types enumeration, before a run row is ever created, so the
    # operator sees "Registered target types: ..." rather than a mid-loop crash. The BYO
    # HTTP-endpoint path resolves through a factory, not a registered target, so skip it.
    if req.http_endpoint is None:
        try:
            container.get_target(req.target_kind)
        except NoTargetRegisteredError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Halt-certification gate (spec US-13): refuse new runs when white-box recall is
    # below the red line.
    async with session_scope() as session:
        halt = await halt_state(session)
    # E2: the devmode override bypasses the launch guard for manual testing; the banner
    # still reports the real halt (the override never changes the displayed metric).
    if halt["halted"] and not get_halt_override():
        raise HTTPException(status_code=409, detail=halt["message"])
    # Budget gate (cr-f4): refuse a new run once the global real-LLM cap is reached, so a
    # public endpoint can never spend without bound.
    global_cap = load_settings().global_budget_dollars
    async with session_scope() as session:
        spent = await global_spend(session)
    if global_cap > 0 and spent >= global_cap:
        raise HTTPException(
            status_code=402,
            detail=f"Global LLM budget reached: ${spent:.4f} of ${global_cap:.2f}")
    if (req.spec_yaml is None) == (req.human_spec is None):
        raise HTTPException(
            status_code=422, detail="provide exactly one of spec_yaml or human_spec"
        )

    source_text: HumanSpec | None = None
    compiler_name = "yaml"
    try:
        if req.human_spec is not None:
            source_text = HumanSpec(
                task=req.human_spec.task,
                failure_conditions=tuple(req.human_spec.failure_conditions),
                hidden_tests=tuple(req.human_spec.hidden_tests),
            )
            sealed = await container.spec_compiler.compile(
                source_text, target_kind=req.target_kind, shape=Shape(req.shape)
            )
            compiler_name = container.spec_compiler.name
        else:
            assert req.spec_yaml is not None  # guarded above
            sealed = SealedSpec.from_yaml(req.spec_yaml)
    except HTTPException:
        raise
    except Exception as exc:  # bad spec is a typed 422 to the caller, not a crash
        raise HTTPException(status_code=422, detail=f"Invalid spec: {exc}") from exc

    if req.mode not in ("redteam", "coevolution"):
        raise HTTPException(status_code=422, detail=f"unknown mode {req.mode!r}")
    if req.target_kind == "code_agent" and req.mode == "coevolution":
        raise HTTPException(
            status_code=422,
            detail="co-evolution is not yet wired for the code-agent — use red-team mode "
                   "(it writes + runs the code and the panel grades it)")

    # Resolve the agent target (Shape 2): a BYO model+prompt, a built-in demo, or a BYO
    # HTTP endpoint — mutually exclusive.
    agent_config: AgentConfig | None = None
    agent_source = "byo"
    http_cfg: HttpEndpointConfig | None = None
    try:
        if req.http_endpoint is not None:
            if req.agent is not None or req.demo_agent is not None:
                raise ValueError("provide only one of agent / demo_agent / http_endpoint")
            if req.mode == "coevolution":
                raise ValueError(
                    "co-evolution can't rewrite a remote agent's prompt — use red-team mode "
                    "for an HTTP endpoint")
            http_cfg = HttpEndpointConfig(
                name=req.http_endpoint.name or "byo-http", endpoint=req.http_endpoint.endpoint,
                input_field=req.http_endpoint.input_field,
                output_field=req.http_endpoint.output_field, method=req.http_endpoint.method,
                headers=dict(req.http_endpoint.headers), timeout=req.http_endpoint.timeout)
            validate_http_endpoint(http_cfg)
        elif req.agent is not None:
            agent_config = AgentConfig(
                name=req.agent.name or "byo-agent", model=req.agent.model,
                system_prompt=req.agent.system_prompt, params=dict(req.agent.params))
            validate_agent_config(agent_config)
        elif req.demo_agent is not None:
            agent_config = demo_agent(req.demo_agent)
            agent_source = "demo"
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid agent: {exc}") from exc

    target_spec = TargetSpec(target_kind=req.target_kind, shape=req.shape, artifact_ref="")
    budget = AttackBudget(max_rounds=req.budget_rounds, max_dollars=req.budget_dollars)
    run_id = await create_run(
        target_spec, sealed, budget, source_text=source_text, compiler=compiler_name
    )

    if agent_config is not None or http_cfg is not None:
        async with session_scope() as session:
            run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
            if agent_config is not None:
                run.agent_config_id = await save_agent_config(
                    session, agent_config, run_id=str(run_id), source=agent_source)
            if http_cfg is not None:
                run.target_http = http_cfg.to_dict()

    if req.mode == "coevolution":
        coro = run_coevolution(
            run_id, container,
            coevo_rounds=req.coevo_rounds, attacks_per_round=req.attacks_per_round)
    else:
        coro = run_loop(run_id, container)
    task = asyncio.create_task(coro)
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


@app.get("/runs")
async def list_runs(limit: int = 25) -> list[dict[str, object]]:
    """Recent runs, newest first — lets every screen default to the latest run when no
    ?run= is given (cr-e3)."""
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(Run).order_by(Run.created_at.desc()).limit(max(1, min(limit, 200))))
        ).scalars().all()
    return [
        {
            "runId": r.id, "status": r.status, "target_kind": r.target_kind,
            "shape": r.shape, "created_at": r.created_at.isoformat(),
            "white_box_recall": r.white_box_recall, "agent_config_id": r.agent_config_id,
        }
        for r in rows
    ]


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
        metrics = await compute_metrics(session, run_id)
        metrics["halt"] = await halt_state(session)
        metrics["trust"] = await compute_trust(session, run_id)
    return metrics


@app.get("/budget")
async def get_budget(run_id: str | None = None) -> dict[str, object]:
    """Real-LLM cost meter + caps (cr-f4): global spend vs the global cap, and a run's
    spend vs its per-run cap. The hard guard that makes a public real-Claude run safe."""
    settings = load_settings()
    per_run_cap = 0.0
    async with session_scope() as session:
        if run_id is not None:
            run = (
                await session.execute(select(Run).where(Run.id == run_id))
            ).scalar_one_or_none()
            per_run_cap = run.budget_dollars if run is not None else 0.0
        return await budget_status(
            session, run_id=run_id, per_run_cap=per_run_cap,
            global_cap=settings.global_budget_dollars)


@app.get("/trust")
async def get_trust(run_id: str | None = None) -> dict[str, object]:
    """The headline trust score (cr-f1): how often the system fails silently past every
    check — a measured floor on trust, with its honest caveats."""
    async with session_scope() as session:
        return await compute_trust(session, run_id)


@app.get("/halt")
async def get_halt() -> dict[str, object]:
    """Halt-certification state for the global banner (spec US-13)."""
    async with session_scope() as session:
        return await halt_state(session)


@app.get("/runs/{run_id}/verdicts")
async def list_verdicts(run_id: str) -> list[dict[str, object]]:
    async with session_scope() as session:
        rows = (
            await session.execute(select(VerdictRow).where(VerdictRow.run_id == run_id))
        ).scalars().all()
        # Which pass each verdict belongs to (D1): the attack carries white_box.
        attacks = (
            await session.execute(select(AttackRow).where(AttackRow.run_id == run_id))
        ).scalars().all()
    white_box_by_attack = {a.id: a.white_box for a in attacks}
    return [
        {
            "verdictId": v.id, "attackId": v.attack_id, "outcome": v.outcome,
            "tally": v.tally, "threshold": v.threshold,
            "white_box": white_box_by_attack.get(v.attack_id, False),
            "fired": [vote["oracle"] for vote in v.votes if vote.get("fired")],
        }
        for v in rows
    ]


@app.get("/coevolution/{run_id}")
async def get_coevolution(run_id: str) -> list[dict[str, object]]:
    """The co-evolution series for a run (cr-d4): per round, ASR (the agent's failure
    rate), detection, the agent config version it ran, and the blue's before/after
    held-out safe-rate — the curves the dashboard plots (spec US-7)."""
    async with session_scope() as session:
        rounds = await coevolution_series(session, run_id)
    return [
        {
            "round": r.round_index, "asr": r.asr, "detection": r.detection,
            "config_version": r.config_version, "n_attacks": r.n_attacks,
            "n_caught": r.n_caught, "patch_id": r.patch_id,
            "safe_before": r.safe_before, "safe_after": r.safe_after,
            "summary": r.audit_trace.get("patch_summary"),
            "validated": r.audit_trace.get("validated"),
            "new_version": r.audit_trace.get("new_version"),
        }
        for r in rounds
    ]


@app.post("/admin/inject-contamination-demo")
async def inject_contamination_demo() -> dict[str, object]:
    """Debug route (PR3 port C2): seed a deliberately CONTAMINATED blue patch so the operator
    can see the Blue Patch Review refuse it. The held-out ids overlap the training ids, so the
    real HoldoutValidator raises HoldoutContamination; we persist that message on a patch with
    NO after-recall (a contaminated patch earns no recovery claim) and return its ids."""
    overlap_ids = ["atk-7", "atk-12", "atk-19", "atk-23", "atk-31"]
    try:
        HoldoutValidator().assert_disjoint(set(overlap_ids), set(overlap_ids))
        message = ""  # unreachable: the sets fully overlap
    except HoldoutContamination as exc:
        message = str(exc)
    run_id = new_id("run")
    patch_id = new_id("patch")
    async with session_scope() as session:
        session.add(Run(
            id=run_id, status="complete", target_kind="agent", shape="shape2_agent",
            budget_rounds=1, budget_dollars=0.0))
        await session.flush()  # the round's FK needs the run row to exist first
        await save_coevolution_round(
            session, run_id=run_id, round_index=0, config_version=1, n_attacks=5,
            n_caught=0, asr=1.0, detection=0.0, patch_id=patch_id,
            safe_before=0.5, safe_after=None,
            audit={"contamination": message, "validated": False, "new_version": 1,
                   "sections": []})
    return {"runId": run_id, "patch_id": patch_id}


@app.get("/blue/{patch_id}")
async def get_blue_patch(patch_id: str) -> dict[str, object]:
    """One blue hardening patch (cr-d4): the rewritten system prompt, the before/after
    held-out safe-rate, and whether it validated (spec US-7)."""
    async with session_scope() as session:
        row = (
            await session.execute(
                select(CoevolutionRoundRow).where(CoevolutionRoundRow.patch_id == patch_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="patch not found")
        new_version = row.audit_trace.get("new_version")
        cfg = (
            await session.execute(
                select(AgentConfigRow).where(
                    AgentConfigRow.run_id == row.run_id,
                    AgentConfigRow.version == new_version))
        ).scalar_one_or_none()
    return {
        "patch_id": patch_id, "runId": row.run_id, "round": row.round_index,
        "base_version": row.config_version, "new_version": new_version,
        "safe_before": row.safe_before, "safe_after": row.safe_after,
        "validated": row.audit_trace.get("validated"),
        "summary": row.audit_trace.get("patch_summary"),
        "new_system_prompt": cfg.system_prompt if cfg is not None else None,
        # C1/C3: the three labelled patch sub-sections (Proposal, Rewrite/Retrain, Holdout
        # validation) the Blue Patch Review renders.
        "sections": row.audit_trace.get("sections", []),
        # C2: a non-empty contamination message means the held-out set overlapped training;
        # the review shows a red banner and NO recovery claim.
        "contamination": row.audit_trace.get("contamination"),
    }


@app.get("/attacks/{attack_id}/replay")
async def replay_attack(attack_id: str) -> dict[str, object]:
    """Deterministic replay + diff (cr-e4, spec US-5): re-run the verification ensemble on
    the stored producer output and compare to the persisted verdict. With deterministic
    oracles the replay is byte-equal — the audit-row replayer's proof that a verdict is
    reproducible."""
    container = get_container()
    async with session_scope() as session:
        atk = (
            await session.execute(select(AttackRow).where(AttackRow.id == attack_id))
        ).scalar_one_or_none()
        if atk is None:
            raise HTTPException(status_code=404, detail="attack not found")
        verdict = (
            await session.execute(select(VerdictRow).where(VerdictRow.attack_id == attack_id))
        ).scalar_one_or_none()
        spec = await resolve_spec(session, atk.run_id)
    stored_output = dict(
        verdict.producer_output if verdict is not None
        else atk.audit_trace.get("producer_output", {}))
    attack = Attack(
        attack_id=AttackId(atk.id), run_id=RunId(atk.run_id), round_index=atk.round_index,
        tactic=atk.tactic, payload=dict(atk.payload), rationale=atk.rationale,
        seed=atk.seed, white_box=atk.white_box, hybrid=atk.hybrid)
    oracles = container.oracles_for(spec.target_kind)
    replayed = await container.verify(oracles, spec, attack, stored_output)
    identical = (
        verdict is not None
        and abs(replayed.tally - verdict.tally) < 1e-9
        and str(replayed.outcome) == verdict.outcome)
    # Serialization round trip (PR3 port A3): the stored votes deserialize and re-serialize
    # byte-identical, the audit-row replayer's proof that a persisted verdict cannot have
    # drifted from the shape the aggregator wrote. We surface BOTH the stored votes JSON and
    # the round-tripped votes JSON so the UI can show the two panels side by side.
    round_tripped_votes = (
        [] if verdict is None else [vote_as_json(v) for v in votes_from_json(verdict.votes)]
    )
    votes_round_trip = verdict is not None and round_tripped_votes == list(verdict.votes)
    return {
        "attackId": attack_id, "runId": atk.run_id, "seed": atk.seed,
        "stored": None if verdict is None else {
            "tally": verdict.tally, "outcome": verdict.outcome,
            "fired": [v["oracle"] for v in verdict.votes if v.get("fired")]},
        "replayed": {
            "tally": replayed.tally, "outcome": str(replayed.outcome),
            "fired": [str(v.oracle) for v in replayed.votes if v.fired]},
        "identical": identical,
        "votesRoundTrip": votes_round_trip,
        "storedVotes": None if verdict is None else list(verdict.votes),
        "roundTrippedVotes": round_tripped_votes,
    }


@app.get("/spec-history")
async def get_spec_history(run_id: str | None = None, limit: int = 50) -> list[dict[str, object]]:
    """Spec versions (cr-e4, spec US-16): the compiled obligations + the plain-English
    source they were compiled from, newest first. Filter by run."""
    async with session_scope() as session:
        query = select(SpecRow)
        if run_id is not None:
            query = query.where(SpecRow.run_id == run_id)
        rows = (
            await session.execute(query.order_by(SpecRow.created_at.desc()).limit(limit))
        ).scalars().all()
    return [
        {
            "specId": s.id, "runId": s.run_id, "version": s.version,
            "compiler": s.compiler, "target_kind": s.target_kind,
            "source_text": s.source_text, "parent_spec_id": s.parent_spec_id,
            "obligations": s.payload.get("obligations", []),
            "created_at": s.created_at.isoformat(),
        }
        for s in rows
    ]


@app.get("/leaderboard")
async def get_leaderboard(format: str = "json") -> Response:
    """Per-run scoreboard (cr-e4/cr-f3, spec US-13): agents ranked by residual leakiness.
    JSON by default; ?format=jsonl exports the downloadable benchmark."""
    async with session_scope() as session:
        rows = await leaderboard(session)
    if format == "jsonl":
        body = "\n".join(json.dumps(row) for row in rows)
        return Response(content=body, media_type="application/x-ndjson",
                        headers={"X-Row-Count": str(len(rows))})
    return Response(content=json.dumps(rows), media_type="application/json")


@app.get("/debug")
async def get_debug() -> dict[str, object]:
    """Admin/debug system state (cr-e4, spec US-12): run counts, totals, LLM spend."""
    async with session_scope() as session:
        summary = await debug_summary(session)
        summary["health"] = {
            name: s.status for name, s in (await get_container().sink.run_health()).items()}
    return summary


@app.get("/runs/{run_id}/llm_calls")
async def list_llm_calls(run_id: str, attack_id: str | None = None) -> list[dict[str, object]]:
    """Every Anthropic call a run made — prompt, response, tokens, cost — for the dashboard
    Inspect button (cr-b4, spec US-5). Filter by attack_id to inspect one round's calls."""
    async with session_scope() as session:
        query = select(LLMCallRow).where(LLMCallRow.run_id == run_id)
        if attack_id is not None:
            query = query.where(LLMCallRow.parent_action_id == attack_id)
        rows = (await session.execute(query.order_by(LLMCallRow.created_at))).scalars().all()
    return [
        {
            "id": c.id, "pillar": c.pillar, "model": c.model,
            "prompt": c.prompt, "response": c.raw_response, "parsed_output": c.parsed_output,
            "prompt_tokens": c.prompt_tokens, "completion_tokens": c.completion_tokens,
            "dollars": c.dollars, "attackId": c.parent_action_id,
            "created_at": c.created_at.isoformat(),
        }
        for c in rows
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


@app.get("/white-box-brief")
async def get_white_box_brief(target_kind: str) -> dict[str, object]:
    """The white-box brief for a target's WIRED oracle panel (PR3 port D2): the disclosed
    protocol descriptions of exactly the oracles currently wired for ``target_kind`` — drop
    one (via /admin/drop-oracle) and its line disappears."""
    container = get_container()
    wired = {str(o.kind) for o in container.oracles_for(target_kind)}
    protocols = [p for p in oracle_protocols() if p["kind"] in wired]
    return {
        "target_kind": target_kind,
        "oracles": [p["name"] for p in protocols],
        "kinds": sorted(wired),
        "brief": compose_white_box_brief(protocols),
    }


@app.post("/admin/drop-oracle")
async def drop_oracle(target_kind: str, kind: str) -> dict[str, object]:
    """Debug route (PR3 port D2): remove a wired oracle KIND from a target's panel in memory,
    so the operator can watch the white-box brief shrink to the remaining oracles. Restart the
    server (or rebuild the container) to restore the full panel."""
    container = get_container()
    container.oracles[target_kind] = [
        o for o in container.oracles_for(target_kind) if str(o.kind) != kind
    ]
    return {
        "target_kind": target_kind, "dropped": kind,
        "remaining": [str(o.kind) for o in container.oracles_for(target_kind)],
    }


@app.get("/oracle-protocols")
async def get_oracle_protocols() -> list[dict[str, object]]:
    """The disclosed verification scheme (PR3 port B3): each oracle kind's name + the first
    paragraph of its README. Red reads the same text in white-box mode and the strategy
    catalog renders it, so attacker and operator see one disclosed scheme."""
    return oracle_protocols()


@app.get("/catalog")
async def get_catalog(
    run_id: str | None = None, target_kind: str | None = None
) -> list[dict[str, object]]:
    """Strategy catalog: the attacker's distilled, named tactics across runs, with how
    often each was used and how often it slipped the verification panel (spec US-6,
    cr-b2). Target-agnostic; optionally filtered by run or target kind."""
    async with session_scope() as session:
        return await build_catalog(session, target_kind=target_kind, run_id=run_id)


@app.post("/admin/halt-override")
async def set_halt_override_route(enabled: bool) -> dict[str, object]:
    """Debug route (PR3 port E2): arm/disarm the devmode halt-launch override. When ON, a
    new run may launch despite a halt; the dashboard banner keeps reporting the real halt."""
    set_halt_override(enabled)
    return {"override": get_halt_override()}


@app.post("/admin/inject-leaky-run")
async def inject_leaky_run() -> dict[str, object]:
    """Debug route (PR3 port E3): seed a run whose white-box attacks are held-out-confirmed
    failures the panel MISSED (silent failures: a held_out 'fired' vote with a clean outcome,
    tally below threshold). That drives Julian's trust score to 0/F, so the platform halts on
    the TRUST score, not on raw catch rate."""
    run_id = new_id("run")
    async with session_scope() as session:
        # Seed a HEALTHY-looking recall (1.0) alongside silent-failure verdicts (trust 0): the
        # recall gate would NOT halt this run, so the halt is driven purely by Julian's trust
        # score — exactly E3's point that the gate is on trust, not raw catch rate / recall.
        session.add(Run(
            id=run_id, status="complete", target_kind="agent", shape="shape2_agent",
            budget_rounds=3, budget_dollars=0.0, white_box_recall=1.0))
        await session.flush()
        for i in range(3):
            aid = new_id("atk")
            session.add(AttackRow(
                id=aid, run_id=run_id, round_index=i, tactic="leaky", payload={"input": "x"},
                rationale="seeded leaky", white_box=True, hybrid=False, succeeded=True,
                pillar=Pillar.red, seed=f"leaky-{i}", dollars_spent=0.0,
                audit_trace={"producer_output": {"response": "leaks"}}))
            session.add(VerdictRow(
                id=new_id("vdt"), run_id=run_id, attack_id=aid,
                producer_output={"response": "leaks"},
                votes=[{"oracle": "held_out", "fired": True, "weight": 1.0, "obligation": "o",
                        "observation": "held-out ground truth: a real, missed failure",
                        "reason": "the producer leaked and the panel did not catch it",
                        "dollars": 0.0, "seed": f"leaky-{i}", "available": True}],
                tally=1.0, threshold=2.0, outcome="clean", pillar=Pillar.oracles,
                seed=f"leaky-{i}", dollars_spent=0.0,
                audit_trace={"summary": "silent failure: held-out fired, tally below threshold"}))
    return {"runId": run_id}


@app.post("/admin/reload-backend")
async def reload_backend() -> dict[str, object]:
    """Debug route (PR3 port D3): rebuild the in-memory container, the same fresh state a
    server restart produces. The strategy-catalog reuse counts (from persisted attacks +
    verdicts) and the discovery log (file-backed) are unaffected, proving they survive a
    restart rather than living only in process memory."""
    set_container(build_container())
    return {"reloaded": True}


@app.get("/catalog/discovery-log")
async def get_discovery_log(run_id: str | None = None) -> Response:
    """The append-only discovery log as a JSONL download (PR3 port D3): one row per evasion
    (an attack that slipped the panel), persisted so it survives a restart."""
    rows = read_discovery_log(run_id)
    body = "\n".join(json.dumps(r) for r in rows)
    return Response(
        content=body, media_type="application/x-ndjson",
        headers={"X-Row-Count": str(len(rows)),
                 "Content-Disposition": "attachment; filename=discovery-log.jsonl"})


@app.get("/reports/{run_id}")
async def get_report(run_id: str, format: str = "markdown") -> Response:
    """SR 11-7 model risk report (spec US-12, cr-f2): Markdown by default, PDF on
    ?format=pdf for committee distribution."""
    async with session_scope() as session:
        try:
            if format == "pdf":
                pdf = await sr_11_7_pdf(session, run_id)
            else:
                markdown = await sr_11_7_markdown(session, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    if format == "pdf":
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="crucible-{run_id}.pdf"'})
    return Response(content=markdown, media_type="text/markdown")


# Bumped whenever the SPA shell changes, so the redirect target is a fresh cache key and
# a browser that cached an older /app/ index can't keep serving it (cr UI deploy hardening).
_APP_VERSION = "2"


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app/?v=" + _APP_VERSION)


class _NoCacheStatic(StaticFiles):
    """Serve the dashboard with no-store so browsers never pin a stale shell. Without
    this, a cached index.html (an old build redirected to a mockup) keeps loading even
    after a redeploy — the user never sees the new app until they clear their cache."""

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        return response


# Serve the single-page dashboard at /app. The JSON API routes above are matched first;
# this mount is the catch-all for the SPA shell + its assets.
_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
if _FRONTEND.is_dir():
    app.mount("/app", _NoCacheStatic(directory=str(_FRONTEND), html=True), name="frontend")
