"""The orchestrator loop. Per constitution.md section 2, ``loop.py`` carries no
business logic: it calls interfaces in sequence and writes audit rows, emitting each
to the Measure sink. Slice 0 lands run creation and the run-lifecycle scaffold; the
red -> verify -> harden -> measure body fills in as the pillars land (slice 1 onward)."""

from __future__ import annotations

from sqlalchemy import select

from orchestrator.wiring import Container
from shared.persistence.db import session_scope
from shared.persistence.models import Run, SpecRow
from shared.telemetry.log import get_logger
from shared.types.core import AttackBudget, TargetSpec
from shared.types.enums import RunStatus
from shared.types.ids import RunId, new_id
from shared.types.sealed_spec import SealedSpec

_log = get_logger("orchestrator.loop")


async def create_run(
    target_spec: TargetSpec,
    sealed_spec: SealedSpec,
    budget: AttackBudget,
) -> RunId:
    """Persist a new run and its sealed spec; return the run id. The spec lives in the
    ``specs`` table, read by oracles through a server-side resolver the producer cannot
    reach (constitution.md section 3)."""
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
                payload={
                    "spec_id": sealed_spec.spec_id,
                    "obligations": [o.obligation_id for o in sealed_spec.obligations],
                    "invariants": [i.invariant_id for i in sealed_spec.invariants],
                },
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


async def run_loop(run_id: RunId, container: Container) -> None:
    """Drive one run to completion. Slice 0: lifecycle only (no pillars wired yet).

    Exceptions are NOT swallowed inside the loop body; on failure the run is marked
    failed with a typed error and the exception re-raised (constitution.md section 8).
    """
    sink = container.sink
    await _set_status(run_id, RunStatus.running)
    await sink.emit(run_id, "run_started", {"run_id": str(run_id)})
    try:
        # red -> verify -> harden -> measure loop body lands in slice 1+.
        await _set_status(run_id, RunStatus.complete)
        await sink.emit(run_id, "run_complete", {"run_id": str(run_id)})
        _log.info("run_complete", run_id=str(run_id))
    except Exception as exc:
        await _set_status(run_id, RunStatus.failed, error=repr(exc))
        await sink.emit(run_id, "run_failed", {"run_id": str(run_id), "error": repr(exc)})
        raise
