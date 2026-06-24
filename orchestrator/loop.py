"""The orchestrator loop.

Per coding-practices.md section 2, this file calls interfaces in sequence and
writes audit rows; it holds no business logic and no conditionals that belong
in a module. Slice 1 drove a single submit through the wired target; slice 10
adds the verify step: every wired oracle votes over the produced output and the
aggregator folds the votes into one persisted verdict. The red search that
supplies real adversarial inputs lands in slice 11, and the measure emit step
lands in slice 15; each slots into this sequence without reshaping it.
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
from shared.persistence.models import Verdict as VerdictRow
from shared.telemetry import get_logger
from shared.types import (
    AttackId,
    OracleVote,
    RunId,
    RunStatus,
    SealedSpec,
    TargetOutput,
    TargetType,
    VerdictDecision,
    VerdictId,
)

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

        attack_id = AttackId.new()
        attack_row = AttackRow(
            id=attack_id.value,
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

        await self._verify_and_persist(run_id, attack_id, run.seed, spec, probe_input, output)

        run.status = RunStatus.COMPLETE.value
        await self.session.commit()
        log.info("loop_round_complete", run_id=run_id, target_type=run.target_type)

    async def _verify_and_persist(
        self,
        run_id: str,
        attack_id: AttackId,
        seed: str,
        spec: SealedSpec,
        attack_input: dict[str, Any],
        output: TargetOutput,
    ) -> None:
        """Run every wired oracle over the output, aggregate, and persist the verdict.

        The aggregator is the single place that turns the votes into a pass-or-
        caught decision (modules/oracles/aggregator.py); the loop only sequences
        the oracle calls and writes the row, holding no aggregation logic itself
        (coding-practices.md section 2).
        """
        votes = await self._collect_votes(run_id, spec, attack_input, output)
        verdict = self.registry.aggregator.aggregate(
            votes,
            run_id=RunId(run_id),
            attack_id=attack_id,
            verdict_id=VerdictId.new(),
        )
        self.session.add(
            VerdictRow(
                id=verdict.verdict_id.value,
                run_id=run_id,
                attack_id=attack_id.value,
                passed=verdict.passed,
                tally=verdict.tally,
                votes=self.registry.aggregator.votes_as_json(verdict.votes),
                pillar="oracles",
                dollars_spent=Decimal("0"),
                seed=seed,
                audit_trace=verdict.audit.as_json(),
                parent_action_id=attack_id.value,
            )
        )

    async def _collect_votes(
        self,
        run_id: str,
        spec: SealedSpec,
        attack_input: dict[str, Any],
        output: TargetOutput,
    ) -> tuple[OracleVote, ...]:
        """Ask each oracle to verify, recording a failed oracle as UNAVAILABLE.

        A crashing or timed-out oracle does not abort the round and is never
        guessed into a pass or fail: it is recorded as an UNAVAILABLE vote with
        the error, and the aggregator reports on the remaining votes
        (ARCHITECTURE.md section 3 failure modes). The error rides the vote
        reason so the verdict view can show exactly which oracle could not run
        and why.
        """
        obligation_id = spec.obligations[0].id if spec.obligations else None
        votes: list[OracleVote] = []
        for oracle in self.registry.oracles:
            try:
                votes.append(await oracle.verify(spec, attack_input, output))
            except Exception as exc:  # recorded as UNAVAILABLE, never swallowed
                log.warning(
                    "oracle_unavailable",
                    run_id=run_id,
                    oracle=oracle.name,
                    error=f"{type(exc).__name__}: {exc}",
                )
                votes.append(
                    OracleVote(
                        oracle_name=oracle.name,
                        decision=VerdictDecision.UNAVAILABLE,
                        weight=oracle.weight,
                        reason=f"oracle could not run: {type(exc).__name__}: {exc}",
                        obligation_id=obligation_id,
                    )
                )
        return tuple(votes)
