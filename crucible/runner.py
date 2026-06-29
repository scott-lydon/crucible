"""Slice 2: the headless run driver.

``crucible run`` runs the eligibility gate FIRST (no spend), and only if not INELIGIBLE
drives the EXISTING loop (orchestrator.loop.run_loop / run_coevolution) end to end against
the real modules. The loop is driven through a FileTraceSink, the same MeasureSink seam the
web run uses, so every stage streams to the terminal and lands in trace.jsonl. No stub or
sample data anywhere on this path: the targets, oracles, and agents are the wired ones."""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import TYPE_CHECKING, Any

from crucible.artifacts import RunArtifacts, append_index
from crucible.eligibility import check_eligibility
from crucible.local_db import init_local_db
from crucible.specs import SpecResolutionError, resolve_sealed_spec
from crucible.suitability import assess_suitability
from shared.obs.emit import EventType, Tracer
from shared.obs.sink import FileTraceSink
from shared.types.enums import Shape
from shared.types.ids import RunId, new_id
from shared.types.sealed_spec import SealedSpec

if TYPE_CHECKING:
    from crucible.eligibility import Eligibility
    from orchestrator.interfaces import Target
    from orchestrator.wiring import Container


def _say(*parts: object) -> None:
    """Human/info output to stderr so stdout stays a pure JSON event stream for piping."""
    print(*parts, file=sys.stderr)


def _print_artifacts_block(arts: RunArtifacts) -> None:
    _say("\nArtifacts:")
    for path in sorted(arts.root.rglob("*")):
        if path.is_file():
            _say(f"  {path}")
    _say(f"\nOpen the report:  crucible report --open {arts.run_id}\n")


def _llm_mode() -> str:
    """real if any CRUCIBLE_REAL_* flag is set (the demo requires this), else mock. The
    demo-authenticity observer reads this to certify MOCK_LLM was off for the capture."""
    import os
    real = any(k.startswith("CRUCIBLE_REAL_") and v == "1" for k, v in os.environ.items())
    return "real" if real else "mock"


def cmd_run(args: argparse.Namespace) -> int:
    from orchestrator.wiring import get_container

    run_id = RunId(new_id("run"))
    arts = RunArtifacts.for_run(run_id).ensure()
    tracer = Tracer(run_id, arts.root, stream=args.stream, emoji=not args.no_emoji)
    container = get_container()

    tracer.emit(EventType.run_start, {
        "target": args.target, "rounds": args.rounds,
        "max_dollars": args.max_dollars, "llm_mode": _llm_mode(),
        "mode": "coevolution" if args.coevolution else "redteam"})

    # --- eligibility (before any spend) ------------------------------------
    if args.target not in container.targets:
        elig = check_eligibility(args.target, _empty_spec(args.target), container=container)
        return _reject(tracer, arts, elig, run_id, args.target)

    target = container.get_target(args.target)
    try:
        spec = resolve_sealed_spec(target, args.spec)
    except SpecResolutionError as exc:
        from crucible.eligibility import Eligibility, EligibilityReason, EligibilityVerdict
        elig = Eligibility(
            EligibilityVerdict.ineligible, args.target,
            [EligibilityReason("spec_unparseable", str(exc), "Provide a valid --spec YAML.")])
        return _reject(tracer, arts, elig, run_id, args.target)

    elig = check_eligibility(args.target, spec, container=container)
    tracer.emit(EventType.eligibility_checked, {
        "verdict": str(elig.verdict),
        "reason": "; ".join(r.message for r in elig.reasons),
        "ensemble": elig.ensemble, "caveats": elig.caveats})
    arts.write_eligibility(elig.to_dict(), tracer=tracer)
    if elig.is_ineligible:
        return _reject(tracer, arts, elig, run_id, args.target, already_checked=True)

    # --- suitability (never halts) -----------------------------------------
    suit = assess_suitability(args.target, spec, container=container)
    for w in suit.warnings:
        tracer.emit(EventType.suitability_assessed, {
            "grade": str(suit.grade), "reason": w.reason,
            "consequence": w.consequence_if_run_anyway, "mitigation": w.mitigation})
    if not suit.warnings:
        tracer.emit(EventType.suitability_assessed, {"grade": str(suit.grade), "reason": ""})
    arts.write_suitability(suit.to_dict(), tracer=tracer)

    tracer.emit(EventType.spec_sealed, {
        "obligations": len(spec.obligations), "invariants": len(spec.invariants),
        "holdout_generator_kind": spec.holdout_generator_kind})

    rounds = args.rounds
    if args.cap_preview:
        rounds = min(rounds, 1)
        _say(f"[cap-preview] running {rounds} round(s) then stopping; "
              f"re-run without --cap-preview for the full {args.rounds}-round run.")

    # --- drive the existing loop through the file-trace sink ----------------
    # Unwrap any prior FileTraceSink so we never nest (a nested wrapper would keep a
    # previous run's tracer alive and fire into its now-stale stream).
    prior = container.sink
    base_sink = prior.inner if isinstance(prior, FileTraceSink) else prior
    container.sink = FileTraceSink(tracer, inner=base_sink)
    try:
        asyncio.run(_drive(run_id, container, target, spec, rounds, args, tracer, arts))
    except Exception as exc:  # noqa: BLE001 — surface ANY run failure as a terminal trace event
        import os
        import traceback
        if os.environ.get("CRUCIBLE_DEBUG"):
            traceback.print_exc()
        tracer.emit(EventType.run_end, {"status": "error", "error": repr(exc)})
        append_index({"run_id": str(run_id), "target": args.target, "status": "error",
                      "error": repr(exc)})
        _print_artifacts_block(arts)
        _say(f"run failed: {exc!r}")
        return 1

    _print_artifacts_block(arts)
    return 0


async def _drive(
    run_id: RunId,
    container: Container,
    target: Target,
    spec: SealedSpec,
    rounds: int,
    args: argparse.Namespace,
    tracer: Tracer,
    arts: RunArtifacts,
) -> None:
    from sqlalchemy import select

    from modules.measure.metrics import compute_metrics
    from modules.measure.report import sr_11_7_markdown
    from orchestrator.loop import create_run, run_coevolution, run_loop
    from shared.persistence.db import session_scope
    from shared.persistence.models import Run, VerdictRow
    from shared.types.core import AttackBudget, TargetSpec

    await init_local_db(arts.root / "crucible.db")

    target_spec = TargetSpec(target_kind=target.kind, shape=spec.shape, artifact_ref="")
    budget = AttackBudget(max_rounds=rounds, max_dollars=args.max_dollars)
    await create_run(target_spec, spec, budget, run_id=run_id)

    if args.coevolution and container.blue_for(target.kind) is not None:
        await run_coevolution(run_id, container, coevo_rounds=rounds, attacks_per_round=3)
    else:
        await run_loop(run_id, container)

    # --- artifacts from the real persisted rows ----------------------------
    async with session_scope() as session:
        run_row = (await session.execute(
            select(Run).where(Run.id == str(run_id)))).scalar_one()
        run_status = str(run_row.status)
        run_error = run_row.error
        verdicts = list((await session.execute(
            select(VerdictRow).where(VerdictRow.run_id == str(run_id)))).scalars().all())
        for v in verdicts:
            arts.write_verdict(str(v.id), {
                "verdict_id": str(v.id), "attack_id": str(v.attack_id),
                "producer_output": v.producer_output, "votes": v.votes,
                "tally": float(v.tally), "threshold": float(v.threshold),
                "outcome": v.outcome, "seed": v.seed,
                "dollars_spent": float(v.dollars_spent)}, tracer=tracer)
            if any(vote.get("oracle") == "held_out" and vote.get("fired") for vote in v.votes) \
                    and v.outcome != "caught":
                row = {"verdict_id": str(v.id), "attack_id": str(v.attack_id),
                       "outcome": v.outcome, "votes": v.votes}
                arts.append_catalog(row, tracer=tracer)
                tracer.emit(EventType.catalog_hit, {
                    "verdict_id": str(v.id), "attack_id": str(v.attack_id)})

        metrics = await compute_metrics(session, str(run_id))
        sr117 = await sr_11_7_markdown(session, str(run_id))

    tiles = metrics["tiles"]
    # The final metric_update mirrors metrics.json exactly (Slice 3: no divergence).
    tracer.emit(EventType.metric_update, {
        "asr": tiles["undetected_hack_rate"],
        "recall": tiles["white_box_catch_rate"],
        "gap": tiles["validation_vs_holdout_gap"],
        "spend": metrics["detail"]["dollars_total"]})
    arts.write_metrics(metrics, tracer=tracer)
    arts.write_text(arts.sr117, sr117, kind="sr-117", tracer=tracer)
    arts.write_text(arts.report, _report_md(run_id, target.kind, metrics), kind="report",
                    tracer=tracer)

    if run_status == "halted":
        tracer.emit(EventType.halt_check, {"halt": True, "reason": run_error})
    tracer.emit(EventType.run_end, {"status": run_status,
                                    "verdicts": metrics["verdicts"], "error": run_error})
    append_index({"run_id": str(run_id), "target": target.kind, "status": run_status,
                  "verdicts": metrics["verdicts"],
                  "white_box_catch_rate": tiles["white_box_catch_rate"]})


def _report_md(run_id: RunId, target_kind: str, metrics: dict[str, Any]) -> str:
    t = metrics["tiles"]
    d = metrics["detail"]

    def pct(v: float | None) -> str:
        return "Not yet measured" if v is None else f"{v * 100:.1f}%"

    return (
        f"# Crucible run report — `{run_id}`\n\n"
        f"- Target: `{target_kind}`\n"
        f"- Verdicts examined: {metrics['verdicts']}\n"
        f"- Producer wrongness (held-out ground truth): {d['producer_wrong_total']}\n"
        f"- Ensemble catches: {d['caught_total']}\n\n"
        f"## Headline metrics (real, from this run's verdicts)\n"
        f"- Black-box catch rate: {pct(t['black_box_catch_rate'])}\n"
        f"- White-box catch rate: {pct(t['white_box_catch_rate'])}\n"
        f"- Black-box vs white-box gap: {pct(t['validation_vs_holdout_gap'])}\n"
        f"- Undetected-hack rate: {pct(t['undetected_hack_rate'])}\n"
        f"- LLM spend: ${d['dollars_total']:.4f}\n\n"
        f"Every number above is computed from `trace.jsonl` / the run's verdict rows; "
        f"a blank tile renders as \"Not yet measured\", never a placeholder zero.\n")


def _reject(
    tracer: Tracer,
    arts: RunArtifacts,
    elig: Eligibility,
    run_id: RunId,
    target_kind: str,
    *,
    already_checked: bool = False,
) -> int:
    if not already_checked:
        tracer.emit(EventType.eligibility_checked, {
            "verdict": str(elig.verdict),
            "reason": "; ".join(r.message for r in elig.reasons)})
        arts.write_eligibility(elig.to_dict(), tracer=tracer)
    tracer.emit(EventType.run_rejected, {
        "reason": "; ".join(f"{r.code}: {r.message} -> {r.fix}" for r in elig.reasons)})
    tracer.emit(EventType.run_end, {"status": "rejected"})
    append_index({"run_id": str(run_id), "target": target_kind, "status": "rejected",
                  "reason": "; ".join(r.code for r in elig.reasons)})
    _print_artifacts_block(arts)
    _say("RUN REJECTED: no spend. Reasons:")
    for r in elig.reasons:
        _say(f"  [{r.code}] {r.message}\n      fix: {r.fix}")
    return 2


def _empty_spec(target_kind: str) -> SealedSpec:
    return SealedSpec(
        spec_id="none", target_kind=target_kind, shape=Shape.shape2_agent,
        obligations=(), invariants=(), holdout_generator_kind="llm_generated")
