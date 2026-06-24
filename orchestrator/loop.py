"""The orchestrator loop.

Per coding-practices.md section 2, this file calls interfaces in sequence and
writes audit rows; it holds no business logic and no conditionals that belong
in a module. Slice 1 drives a single submit through the wired target and
persists the result, proving the spine target to orchestrator to Postgres.
The red search that supplies real adversarial inputs lands in slice 11, and
the oracle verify and measure emit steps land in slices 5 to 10 and 15; each
slots into this sequence without reshaping it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.errors import RunNotFoundError
from orchestrator.wiring import Registry
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import Run
from shared.telemetry import get_logger
from shared.types import AttackId, RunStatus, SealedSpec, TargetType

log = get_logger("orchestrator.loop")


def _seed_probe_input(spec: SealedSpec) -> dict[str, Any]:
    """A deterministic probe input so the spine runs before the red agent exists.

    Replaced in slice 11, when the red agent supplies real adversarial inputs.
    Kept deterministic so a replay reproduces the same row.
    """
    return {"probe": "seed", "obligation": spec.obligations[0].id}


@dataclass(frozen=True, slots=True)
class Loop:
    """Drives one run end to end against the wired target."""

    session: AsyncSession
    registry: Registry

    async def run(self, run_id: str) -> None:
        """Run one round for `run_id`: submit a probe, persist it, complete the run."""
        run = await self.session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(
                f"Run {run_id!r} not found in the runs table. It must be created "
                f"via POST /runs before the loop can drive it."
            )

        run.status = RunStatus.RUNNING.value
        await self.session.flush()

        spec = SealedSpec.from_payload(run.spec_json)
        target = self.registry.target_for(TargetType(run.target_type))

        probe_input = _seed_probe_input(spec)
        output = await target.submit(spec, probe_input)

        attack_row = AttackRow(
            id=AttackId.new().value,
            run_id=run_id,
            tactic="seed-probe",
            payload=probe_input,
            succeeded=False,
            white_box=False,
            hybrid=False,
            pillar="orchestrator",
            dollars_spent=Decimal("0"),
            seed=run.seed,
            audit_trace={
                "summary": "slice-1 seed probe driven through the target",
                "output": output.output,
                "score": output.score,
                "producer_audit": output.audit.as_json(),
            },
        )
        self.session.add(attack_row)

        run.status = RunStatus.COMPLETE.value
        await self.session.commit()
        log.info("loop_round_complete", run_id=run_id, target_type=run.target_type)
