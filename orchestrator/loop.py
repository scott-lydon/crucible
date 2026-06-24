"""The orchestrator loop.

Per coding-practices.md section 2, this file calls interfaces in sequence and
writes audit rows; it holds no business logic and no conditionals that belong
in a module. Slice 1 drove a single seed probe; slice 10 added the oracle
verify step; slice 12 replaces the seed probe with the red search and runs both
passes mandated by US-14:

  1. black-box pass  - the red agent attacks the target knowing only its score.
  2. white-box pass  - the same search, now handed the disclosed oracle scheme.

Each pass produces attempts; the loop drives every attempt through the target
and the oracle ensemble, persists the attack and its verdict, and records an
undetected hack (one that cleared the ensemble) in the strategy catalog. The
attack row's `succeeded` is the reward-hack sense the slice-11 note deferred to
the loop: it got past the oracles (verdict.passed), not merely past the
target's own score. The measure emit step lands in slice 15; it slots into this
sequence without reshaping it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.red import StrategyCatalog, compose_white_box_brief
from orchestrator.errors import RunNotFoundError
from orchestrator.wiring import Registry
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import Run
from shared.persistence.models import Verdict as VerdictRow
from shared.telemetry import get_logger
from shared.types import (
    Attack,
    AttackBudget,
    AttackId,
    Money,
    OracleVote,
    RunId,
    RunStatus,
    SealedSpec,
    TargetOutput,
    TargetType,
    Verdict,
    VerdictDecision,
    VerdictId,
)

log = get_logger("orchestrator.loop")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _default_catalog_jsonl() -> Path:
    """The append-only strategy-catalog discovery log on disk (US-6)."""
    return _REPO_ROOT / "data" / "strategy_catalog.jsonl"


@dataclass(frozen=True, slots=True)
class Loop:
    """Drives one run end to end: black-box then white-box red against the target."""

    session: AsyncSession
    registry: Registry
    catalog_jsonl: Path = field(default_factory=_default_catalog_jsonl)

    async def run(self, run_id: str) -> None:
        """Run one round for `run_id`: black-box then white-box red, then complete."""
        run = await self.session.get(Run, run_id)
        if run is None:
            raise RunNotFoundError(
                f"Run {run_id!r} not found in the runs table. It must be created "
                f"via POST /runs before the loop can drive it."
            )

        run.status = RunStatus.RUNNING.value
        await self.session.flush()

        spec = SealedSpec.from_payload(run.spec_json)
        target_type = TargetType(run.target_type)
        target = self.registry.target_for(target_type)
        budget = AttackBudget(
            max_attempts=run.budget_max_attempts,
            max_dollars=Money(Decimal(run.budget_max_dollars)),
        )

        # Black-box: the attacker knows only the target's own score.
        await self._red_pass(
            run, spec, target, target_type, budget, white_box=False, oracle_scheme=None
        )
        # White-box (US-14): the attacker is handed the disclosed oracle scheme.
        scheme = compose_white_box_brief(
            [(o.name, o.protocol_description) for o in self.registry.oracles]
        )
        await self._red_pass(
            run, spec, target, target_type, budget, white_box=True, oracle_scheme=scheme
        )

        run.status = RunStatus.COMPLETE.value
        await self.session.commit()
        log.info("loop_round_complete", run_id=run_id, target_type=run.target_type)

    async def _red_pass(
        self,
        run: Run,
        spec: SealedSpec,
        target: Any,
        target_type: TargetType,
        budget: AttackBudget,
        *,
        white_box: bool,
        oracle_scheme: str | None,
    ) -> None:
        """Run one red pass and drive every attempt through the oracle ensemble."""
        attacks = await self.registry.red.search(
            spec,
            target,
            budget,
            RunId(run.id),
            white_box=white_box,
            oracle_scheme=oracle_scheme,
        )
        catalog = StrategyCatalog(session=self.session, jsonl_path=self.catalog_jsonl)
        for attack in attacks:
            await self._drive_attempt(run, spec, target, target_type, catalog, attack)

    async def _drive_attempt(
        self,
        run: Run,
        spec: SealedSpec,
        target: Any,
        target_type: TargetType,
        catalog: StrategyCatalog,
        attack: Attack,
    ) -> None:
        """Submit one attempt, verify it, and persist the attack and its verdict.

        A malformed proposal carries no payload to submit; it is persisted as a
        caught (not-succeeded) attempt with no verdict, so it never inflates the
        catch-rate denominator (which counts judged submissions only).
        """
        if not attack.payload:
            self.session.add(self._attack_row(run, attack, succeeded=False))
            await self.session.flush()
            return

        output = await target.submit(spec, attack.payload)
        verdict = await self._verify(run, attack.attack_id, spec, attack.payload, output)

        # The reward-hack sense (ARCHITECTURE.md section 3): an attempt succeeds
        # when it gets past the whole ensemble, not merely the target's score.
        self.session.add(self._attack_row(run, attack, succeeded=verdict.passed, output=output))
        await self.session.flush()  # parent before child: verdict FK -> attacks.id
        self.session.add(self._verdict_row(run, attack.attack_id, verdict))

        if verdict.passed:
            await catalog.record_success(attack, target_type)

    def _attack_row(
        self,
        run: Run,
        attack: Attack,
        *,
        succeeded: bool,
        output: TargetOutput | None = None,
    ) -> AttackRow:
        audit = attack.audit.as_json()
        if output is not None:
            audit = {**audit, "producer_audit": output.audit.as_json(), "output": output.output}
        return AttackRow(
            id=attack.attack_id.value,
            run_id=run.id,
            tactic=attack.tactic,
            payload=attack.payload,
            succeeded=succeeded,
            white_box=attack.white_box,
            hybrid=attack.hybrid,
            pillar="red",
            dollars_spent=attack.dollars_spent.dollars,
            seed=run.seed,
            audit_trace=audit,
        )

    def _verdict_row(self, run: Run, attack_id: AttackId, verdict: Verdict) -> VerdictRow:
        return VerdictRow(
            id=verdict.verdict_id.value,
            run_id=run.id,
            attack_id=attack_id.value,
            passed=verdict.passed,
            tally=verdict.tally,
            votes=self.registry.aggregator.votes_as_json(verdict.votes),
            pillar="oracles",
            dollars_spent=Decimal("0"),
            seed=run.seed,
            audit_trace=verdict.audit.as_json(),
            parent_action_id=attack_id.value,
        )

    async def _verify(
        self,
        run: Run,
        attack_id: AttackId,
        spec: SealedSpec,
        attack_input: dict[str, Any],
        output: TargetOutput,
    ) -> Verdict:
        """Run every wired oracle over the output and aggregate one verdict.

        The aggregator is the single place that turns the votes into a pass-or-
        caught decision (modules/oracles/aggregator.py); the loop only sequences
        the oracle calls and folds them, holding no aggregation logic itself
        (coding-practices.md section 2).
        """
        votes = await self._collect_votes(run.id, spec, attack_input, output)
        return self.registry.aggregator.aggregate(
            votes,
            run_id=RunId(run.id),
            attack_id=attack_id,
            verdict_id=VerdictId.new(),
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
