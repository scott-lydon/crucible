import dataclasses
import uuid
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from modules.blue.code_engineer import BlueCodeEngineer
from modules.measure.corpus_exporter import corpus_entries, corpus_jsonl
from modules.measure.halt_rule import halt_status
from modules.measure.health import (
    HealthInputs,
    health_report,
    run_live_seal_probe,
    run_one_self_test,
)
from modules.measure.metrics import compute_run_metrics
from modules.measure.risk_report import render_risk_report
from orchestrator.db import init_db as init_db  # re-export for tests
from orchestrator.db import session_factory
from orchestrator.full_run import run_white_box_pass, run_with_blue
from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import run_loop
from orchestrator.stream import run_event_stream
from orchestrator.wiring import (
    DEFAULT_THRESHOLD,
    build_components,
    build_components_sparkov,
)
from shared.env import load_env
from shared.persistence import repo
from shared.persistence.models import RunRow
from shared.sandbox import LocalDockerSandbox
from shared.sandbox.base import Sandbox
from shared.types import SealedSpec
from shared.types.enums import OracleKind, Vote

# Test-injection seam. A test may set this to a dict of kwargs forwarded into
# ``build_components_sparkov`` (e.g. mock providers + budget 0) so a sparkov run
# makes ZERO real LLM calls. None => the real demo path (live, bounded providers).
# This is the ONLY way the suite exercises target="sparkov" without billing.
SPARKOV_TEST_OVERRIDES: dict[str, object] | None = None

# Test-injection seam for the /health self-test view. A test may set this to a
# ``HealthInputs`` (with a deterministic sandbox + a mockable anthropic ping) so
# the seal card / probe and the Anthropic leg are exercised with ZERO real LLM
# calls and no Docker dependency. None => the live, introspected inputs.
HEALTH_TEST_INPUTS: object | None = None


def _health_inputs() -> HealthInputs:
    """Assemble the live ``HealthInputs`` for the self-test view.

    Introspects the OFFLINE synth composition (always constructible, no real LLM
    calls, no external data) for the in-process component shapes — the detector,
    adversary, and the six oracles share the same Protocol surface across
    targets, so the synth wiring is a faithful, free stand-in for the smoke
    checks. The real session factory and the real local Docker sandbox adapter
    are wired in so the Postgres / sandbox / seal-probe legs are honest.
    """
    if HEALTH_TEST_INPUTS is not None:
        return cast(HealthInputs, HEALTH_TEST_INPUTS)
    comp = build_components(threshold=DEFAULT_THRESHOLD)
    sandbox: object = LocalDockerSandbox()
    return HealthInputs(
        session_factory=session_factory(),
        detector=comp["detector"],
        adversary=comp["adversary"],
        oracles=cast(Sequence[object], comp["oracles"]),
        sandbox=sandbox,
    )


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    load_env()
    await init_db()
    yield


app = FastAPI(title="Crucible Fraud MVP v0", lifespan=_lifespan)


# Per-target default batch sizes. Sparkov uses the larger demo default so the
# red loop lands MORE evasions, giving the blue expand loop a bigger, more
# representative holdout to recover on. Both stay inside the ``le=200`` bound.
_DEFAULT_BATCH: dict[str, int] = {"sparkov": 120, "synth": 40}


class LaunchRequest(BaseModel):
    target: str = Field("sparkov", pattern="^(sparkov|synth)$")
    rounds: int = Field(3, ge=1, le=5)
    # ``None`` => resolve a target-aware default in ``create_run`` (sparkov=120,
    # synth=40). An explicit value is still bounded to [2, 200].
    batch_size: int | None = Field(None, ge=2, le=200)
    seed: str = "seed-1"
    run_blue: bool = True

    def resolved_batch_size(self) -> int:
        """Caller's batch_size, or the target's demo default when unset."""
        if self.batch_size is not None:
            return self.batch_size
        return _DEFAULT_BATCH.get(self.target, 40)


@app.get("/health")
async def health() -> dict[str, object]:
    """Hierarchical self-test view (US-8) + the producer-sandbox seal card (US-9).

    pillar -> module -> subcomponent, each leaf ``{state, last_self_test, error}``.
    Read-only smoke tests; the Anthropic leg is TOKEN-FREE (key presence / a
    mockable ping), so opening this page never spends money or runs the loop.
    """
    return await health_report(_health_inputs())


@app.post("/health/selftest/{component_id}")
async def post_self_test(component_id: str) -> dict[str, object]:
    """Re-run ONE subcomponent's smoke and return its updated leaf (US-8 button)."""
    try:
        return await run_one_self_test(_health_inputs(), component_id)
    except KeyError as exc:
        raise HTTPException(404, f"unknown component {component_id!r}") from exc


@app.post("/health/seal-probe")
async def post_seal_probe() -> dict[str, object]:
    """Run the live in-sandbox seal probe (US-9 button) and report the result.

    Honest when the live probe cannot run (Docker/gateway unavailable): returns
    ``available=false`` with the reason — never a fabricated ``sealed: true``.
    """
    return run_live_seal_probe(_health_inputs().sandbox)


async def _execute_run(req: LaunchRequest, run_id: str) -> None:
    """Build the requested target's components and drive the run to completion.

    Runs as a FastAPI background task. ``run_loop`` / ``run_with_blue`` own the
    running->complete/failed transitions (and mark failed on exception), so any
    error here is captured against the run row, never swallowed.
    """
    sf = session_factory()
    batch_size = req.resolved_batch_size()
    if req.target == "sparkov":
        overrides = SPARKOV_TEST_OVERRIDES or {}
        build_sparkov = cast(
            Callable[..., dict[str, object]], build_components_sparkov
        )
        comp = build_sparkov(threshold=DEFAULT_THRESHOLD, **overrides)
    else:
        comp = build_components(threshold=DEFAULT_THRESHOLD)

    detector = cast(Detector, comp["detector"])
    adversary = cast(Adversary, comp["adversary"])
    oracles = cast(Sequence[Oracle], comp["oracles"])
    label_fn = cast(Callable[[object], bool], comp["label_fn"])
    generate_fn = cast(Callable[[str, int], list[object]], comp["generate_fn"])
    spec = cast(SealedSpec, comp["spec"])

    # Seal the spec: persist it server-side (app DB creds, in-process) so the
    # harness/oracles resolve it from Postgres while the producer (sandboxed)
    # never gets DB creds or the spec contents — only its input sample. The
    # in-process ``spec`` object continues to drive this run unchanged; sealing
    # is the additive, demonstrable path (US-9 / slice-4).
    async with sf() as s:
        await repo.store_spec(s, run_id, spec)

    # Blue composition needs the sparkov-only seams; synth has no blue arc.
    blue_ready = req.run_blue and "blue_engineer" in comp
    if blue_ready:
        await run_with_blue(
            sf,
            run_id=run_id,
            seed=req.seed,
            n_rounds=req.rounds,
            batch_size=batch_size,
            threshold=DEFAULT_THRESHOLD,
            detector=detector,
            adversary=adversary,
            oracles=oracles,
            label_fn=label_fn,
            generate_fn=generate_fn,
            spec=spec,
            catalog=comp["catalog"],
            engineer_agent=cast(BlueCodeEngineer, comp["blue_engineer"]),
            sandbox=cast(Sandbox, comp["blue_sandbox"]),
            retrain_engineered_fn=cast(
                Callable[..., Detector], comp["retrain_engineered_fn"]
            ),
            load_raw_rows=cast(
                Callable[..., list[dict[str, object]]], comp["load_raw_rows"]
            ),
            load_holdout_raw_rows=cast(
                Callable[..., list[object]], comp["load_holdout_raw_rows"]
            ),
            base_features=cast(Sequence[str], comp["base_features"]),
            raw_columns=cast(Sequence[str], comp["raw_columns"]),
            raw_label_fn=cast(Callable[[object], bool], comp["raw_label_fn"]),
        )
    else:
        await run_loop(
            sf,
            run_id=run_id,
            seed=req.seed,
            n_rounds=req.rounds,
            batch_size=batch_size,
            threshold=DEFAULT_THRESHOLD,
            detector=detector,
            adversary=adversary,
            oracles=oracles,
            label_fn=label_fn,
            generate_fn=generate_fn,
            spec=spec,
        )

    # WHITE-BOX self-test pass (US-14): after the black-box red+blue arc, run an
    # INFORMED red pass whose prompt carries the oracles' verification scheme,
    # then persist black-box vs white-box catch rate + the gap. Sparkov-only
    # (the white-box adversary is wired at the sparkov composition root).
    if "white_box_adversary" in comp:
        await run_white_box_pass(
            sf,
            black_box_run_id=run_id,
            seed=req.seed,
            n_rounds=req.rounds,
            batch_size=batch_size,
            threshold=DEFAULT_THRESHOLD,
            detector=detector,
            white_box_adversary=cast(Adversary, comp["white_box_adversary"]),
            oracles=oracles,
            label_fn=label_fn,
            generate_fn=generate_fn,
            spec=spec,
        )


@app.post("/runs", status_code=201)
async def create_run(
    req: LaunchRequest, background_tasks: BackgroundTasks
) -> dict[str, str]:
    """Launch a Crucible run as a background task; return the run id immediately.

    ``target="sparkov"`` wires the REAL Sparkov victim via
    ``build_components_sparkov`` with LIVE, BOUNDED providers (Sonnet on the red
    loop, Opus on the judge, Sonnet on the blue proposer). A real sparkov run
    therefore makes real (bounded) LLM calls — on the order of ~$0.40 per run.
    ``target="synth"`` uses the cheap offline synthetic victim (no real calls).

    With ``run_blue=true`` (default) a sparkov run also runs the blue recovery
    arc and persists a ``BlueRoundRow``; synth has no blue arc and ignores it.
    Status transitions running -> complete/failed are owned by the loop.
    """
    sf = session_factory()
    # Refuse new launches when certification is HALTED (US-13): the platform will
    # not certify what it cannot defend. Typed 409 body carries the recall +
    # threshold that tripped the red line.
    async with sf() as s:
        status = await halt_status(s)
    if status.halted:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "certification_halted",
                "recall": status.recall,
                "threshold": status.threshold,
            },
        )

    run_id = str(uuid.uuid4())
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id,
                seed=req.seed,
                status="running",
                n_rounds=req.rounds,
                batch_size=req.resolved_batch_size(),
                threshold=DEFAULT_THRESHOLD,
                params_json=req.model_dump(),
            )
        )
        await s.commit()
    background_tasks.add_task(_execute_run, req, run_id)
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        run = await repo.get_run(s, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        verdicts = await repo.verdicts_for_run(s, run_id)
        return {
            "run_id": run.id,
            "status": run.status,
            "seed": run.seed,
            "n_rounds": run.n_rounds,
            "verdict_count": len(verdicts),
        }


@app.get("/runs/{run_id}/verdicts")
async def list_verdicts(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        verdicts = await repo.verdicts_for_run(s, run_id)
        return {"verdicts": [
            {"verdict_id": v.id, "round_id": v.round_id,
             "aggregate_pass": v.aggregate_pass, "fail_weight": v.fail_weight}
            for v in verdicts]}


@app.get("/runs/{run_id}/metrics")
async def get_metrics(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        m = await compute_run_metrics(s, run_id)
        wb = await repo.white_box_metrics_for_run(s, run_id)
    # The white-box gap tile: black-box vs white-box catch rate + the gap. Null
    # rates surface honestly (undefined when a pass had no successful evasions).
    white_box = (
        {
            "black_box_catch_rate": wb.black_box_catch_rate,
            "white_box_catch_rate": wb.white_box_catch_rate,
            "white_box_gap": wb.white_box_gap,
        }
        if wb is not None
        else None
    )
    if m is None:
        not_measured: dict[str, object] = {"status": "Not yet measured"}
        if white_box is not None:
            not_measured["white_box"] = white_box
        return not_measured
    # Single source of truth for the catch rates + gap: the nested ``white_box``
    # object (``None`` until the white-box pass has run). No flat duplicates.
    return {
        "per_round": [dataclasses.asdict(r) for r in m.per_round],
        "baseline_validation_detection": m.baseline_validation_detection,
        "gap": m.gap,
        "white_box": white_box,
    }


@app.get("/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    """Server-Sent Events stream of a run's progress (US-2).

    Tails the run's PERSISTED rows and emits an ``attack`` + ``trace`` event per
    attack (ASR-so-far / rationale), a ``verdict`` event per verdict
    (detection-rate-so-far + pass/fail), and a terminal ``complete`` event when
    the run status is terminal. No new LLM calls — it reads only what the loop
    persisted. Bounded by a wall-clock cap so it always closes cleanly.
    """
    sf = session_factory()

    async def _events() -> AsyncIterator[str]:
        async for chunk in run_event_stream(sf, run_id):
            yield chunk

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/runs/{run_id}/blue")
async def get_blue_round(run_id: str) -> dict[str, object]:
    """The persisted blue recovery round for this run (404 if none ran)."""
    async with session_factory()() as s:
        row = await repo.blue_round_for_run(s, run_id)
        if row is None:
            raise HTTPException(404, "no blue round for run")
        return {
            "run_id": row.run_id,
            "features_added": row.features_added,
            "detection_before": row.detection_before,
            "detection_after": row.detection_after,
            "recovered": row.recovered,
            "n_holdout": row.n_holdout,
            "proposer_rationale": row.proposer_rationale,
            "new_model_ref": row.new_model_ref,
            "iteration_trail": row.iteration_trail,
        }


@app.get("/corpus")
async def get_corpus(run_id: str | None = None) -> dict[str, object]:
    """The seeded-hack corpus table: every successful evasion (optionally one run).

    Honest empty-state: an empty corpus returns ``{"count": 0, "rows": []}``,
    never a placeholder row. ``count`` equals the number of JSONL lines the
    download produces (US-11 invariant).
    """
    async with session_factory()() as s:
        entries = await corpus_entries(s, run_id)
    return {"count": len(entries), "rows": [e.to_dict() for e in entries]}


@app.get("/corpus/export")
async def export_corpus(run_id: str | None = None) -> StreamingResponse:
    """Stream the corpus as a JSONL download (one successful evasion per line).

    The line count EXACTLY equals the ``/corpus`` row count — empty corpus yields
    an empty (zero-line) file, never a fabricated row.
    """
    sf = session_factory()

    async def _stream() -> AsyncIterator[str]:
        async with sf() as s:
            async for line in corpus_jsonl(s, run_id):
                yield line

    return StreamingResponse(
        _stream(),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="corpus.jsonl"'},
    )


@app.get("/reports/{run_id}", response_class=PlainTextResponse)
async def get_report(run_id: str) -> str:
    """The SR 11-7 model risk report for ``run_id`` as Markdown (404 if no run).

    PDF download (US-12) is deferred: a clean pure-Python md->pdf path is not
    available without a heavy new dependency, so the operator dashboard renders
    this Markdown and PDF export is tracked as a follow-up. Every numeric field
    carries its source-row reference inline (`[table:id]`).
    """
    async with session_factory()() as s:
        md = await render_risk_report(s, run_id)
    if md is None:
        raise HTTPException(404, "run not found")
    return md


@app.get("/halt")
async def get_halt() -> dict[str, object]:
    """The certification halt status the dashboard banner reads (US-13)."""
    async with session_factory()() as s:
        return (await halt_status(s)).to_dict()


@app.get("/runs/{run_id}/verdicts/{verdict_id}")
async def get_verdict(run_id: str, verdict_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        votes = await repo.votes_for_verdict(s, verdict_id)
        if not votes:
            raise HTTPException(404, "verdict not found")
        return {
            "verdict_id": verdict_id,
            "run_id": run_id,
            "votes": [
                {
                    "oracle": v.oracle_kind,
                    "vote": v.vote,
                    "weight": v.weight,
                    "reason": v.reason,
                    "evidence": v.evidence_json,
                    "abstained": v.vote == Vote.ABSTAIN.value,
                    "is_llm": v.oracle_kind == OracleKind.LLM_JUDGE.value,
                }
                for v in votes
            ],
        }
