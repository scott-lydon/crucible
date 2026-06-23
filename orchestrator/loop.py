"""The orchestrator loop. Per constitution.md section 2, ``loop.py`` carries no
business logic: it calls interfaces in sequence and writes audit rows, emitting each
to the Measure sink.

Slice 1 lands the per-round red -> submit path against the dummy target. The verify
(oracles), harden (blue) and white-box passes slot into the same loop as their
slices land; the loop runs whatever pillars wiring has registered."""

from __future__ import annotations

from sqlalchemy import select

from orchestrator.wiring import Container
from shared.persistence.db import session_scope
from shared.persistence.models import AttackRow, Run, SpecRow, VerdictRow
from shared.persistence.resolver import resolve_spec
from shared.telemetry.log import get_logger
from shared.types.core import Attack, AttackBudget, TargetSpec, Verdict
from shared.types.enums import Pillar, RunStatus
from shared.types.ids import RunId, new_id
from shared.types.results import ProducerResult
from shared.types.sealed_spec import SealedSpec

_log = get_logger("orchestrator.loop")


async def create_run(
    target_spec: TargetSpec,
    sealed_spec: SealedSpec,
    budget: AttackBudget,
) -> RunId:
    """Persist a new run and its sealed spec; return the run id. The full spec lives
    in the ``specs`` table, read by oracles through a server-side resolver the producer
    container cannot reach (constitution.md section 3)."""
    run_id = RunId(new_id("run"))
    async with session_scope() as session:
        session.add(
            Run(
                id=run_id,
                status=RunStatus.pending,
                target_kind=target_spec.target_kind,
                shape=target_spec.shape,
                budget_rounds=budget.max_rounds,
                budget_dollars=budget.max_dollars,
            )
        )
        session.add(
            SpecRow(
                id=new_id("spec"),
                run_id=run_id,
                target_kind=sealed_spec.target_kind,
                shape=sealed_spec.shape,
                holdout_generator_kind=sealed_spec.holdout_generator_kind,
                payload=sealed_spec.to_dict(),
            )
        )
    _log.info("run_created", run_id=str(run_id), target=target_spec.target_kind)
    return run_id


async def _set_status(run_id: RunId, status: RunStatus, *, error: str | None = None) -> None:
    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status = status
        if error is not None:
            run.error = error


async def _load_context(run_id: RunId) -> tuple[SealedSpec, str, int]:
    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        spec = await resolve_spec(session, run_id)
        return spec, run.target_kind, run.budget_rounds


async def _persist_round(
    run_id: RunId, attack: Attack, result: ProducerResult, verdict: Verdict | None
) -> None:
    async with session_scope() as session:
        session.add(
            AttackRow(
                id=attack.attack_id,
                run_id=run_id,
                round_index=attack.round_index,
                tactic=attack.tactic,
                payload=dict(attack.payload),
                rationale=attack.rationale,
                white_box=attack.white_box,
                hybrid=attack.hybrid,
                # "succeeded" = evaded the oracle ensemble (verdict clean). Whether the
                # producer was truly wrong needs ground truth — set by Measure once the
                # held-out oracle lands (slice 5).
                succeeded=verdict is not None and not verdict.caught,
                pillar=Pillar.red,
                seed=attack.seed,
                dollars_spent=result.dollars,
                audit_trace={
                    "producer_output": dict(result.output),
                    "producer_summary": result.audit.summary,
                    "producer_detail": dict(result.audit.detail),
                },
            )
        )
        if verdict is not None:
            session.add(
                VerdictRow(
                    id=verdict.verdict_id,
                    run_id=run_id,
                    attack_id=attack.attack_id,
                    producer_output=dict(verdict.producer_output),
                    votes=[v.as_dict() for v in verdict.votes],
                    tally=verdict.tally,
                    threshold=verdict.threshold,
                    outcome=str(verdict.outcome),
                    pillar=Pillar.oracles,
                    seed=verdict.seed,
                    dollars_spent=verdict.dollars,
                    audit_trace={"summary": verdict.audit.summary, **verdict.audit.detail},
                )
            )


async def run_loop(run_id: RunId, container: Container) -> None:
    """Drive one run to completion. Exceptions are not swallowed inside the loop body;
    on failure the run is marked failed with a typed error and re-raised
    (constitution.md section 8)."""
    sink = container.sink
    await _set_status(run_id, RunStatus.running)
    await sink.emit(run_id, "run_started", {"run_id": str(run_id)})
    try:
        spec, target_kind, budget_rounds = await _load_context(run_id)
        target = container.get_target(target_kind)
        red = container.red_for(target_kind)
        oracles = container.oracles_for(target_kind)
        last_verdict: Verdict | None = None

        for round_index in range(budget_rounds):
            attack = await red.propose(spec, run_id, round_index, last_verdict, white_box=False)
            result = await target.submit(attack.payload)
            verdict = (
                await container.verify(oracles, spec, attack, result.output) if oracles else None
            )
            await _persist_round(run_id, attack, result, verdict)
            await sink.emit(
                run_id,
                "attack",
                {
                    "attack_id": str(attack.attack_id),
                    "round": round_index,
                    "tactic": attack.tactic,
                    "payload": dict(attack.payload),
                },
            )
            await sink.emit(
                run_id,
                "producer_output",
                {"attack_id": str(attack.attack_id), "output": dict(result.output)},
            )
            if verdict is not None:
                await sink.emit(
                    run_id,
                    "verdict",
                    {
                        "verdict_id": str(verdict.verdict_id),
                        "attack_id": str(attack.attack_id),
                        "outcome": str(verdict.outcome),
                        "tally": verdict.tally,
                        "threshold": verdict.threshold,
                        "summary": verdict.audit.summary,
                    },
                )
                last_verdict = verdict

        await _set_status(run_id, RunStatus.complete)
        await sink.emit(run_id, "run_complete", {"run_id": str(run_id), "rounds": budget_rounds})
        _log.info("run_complete", run_id=str(run_id), rounds=budget_rounds)
    except Exception as exc:
        await _set_status(run_id, RunStatus.failed, error=repr(exc))
        await sink.emit(run_id, "run_failed", {"run_id": str(run_id), "error": repr(exc)})
        raise
