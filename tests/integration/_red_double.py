"""A deterministic RedAgent double for the loop and metric tests.

Returns preset attempts (no LLM, no network) split by box, stamping each with
the run_id the loop passes in, exactly as the real RedSearchAgent does. The
loop's own logic (drive each attempt through the target and the oracle ensemble,
persist, catalog) is what the tests exercise; the red search has its own tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.interfaces import Target
from shared.types import (
    Attack,
    AttackBudget,
    AttackId,
    AuditStep,
    AuditTrace,
    Money,
    RunId,
    SealedSpec,
)


@dataclass(frozen=True, slots=True)
class _Attempt:
    tactic: str
    payload: dict[str, Any]
    white_box: bool
    succeeded: bool


def attempt(
    tactic: str, payload: dict[str, Any], *, white_box: bool, succeeded: bool = False
) -> _Attempt:
    """Describe one preset attempt for the scripted red double.

    ``succeeded`` is the red search's own score-based evasion verdict (the model
    scored the input below the evasion threshold). The loop trusts it for a
    scored target (``oracle_verified == False``); for a code target the oracle
    ensemble decides instead, so it defaults to False.
    """
    return _Attempt(tactic=tactic, payload=payload, white_box=white_box, succeeded=succeeded)


@dataclass(frozen=True, slots=True)
class ScriptedRed:
    """A RedAgent double returning preset attempts, split by box."""

    attempts: list[_Attempt]

    async def search(
        self,
        spec: SealedSpec,
        target: Target,
        budget: AttackBudget,
        run_id: RunId,
        *,
        white_box: bool,
        oracle_scheme: str | None = None,
    ) -> list[Attack]:
        return [
            Attack(
                attack_id=AttackId.new(),
                run_id=run_id,
                tactic=a.tactic,
                payload=a.payload,
                succeeded=a.succeeded,
                white_box=a.white_box,
                hybrid=False,
                dollars_spent=Money.of(0.01),
                audit=AuditTrace(
                    summary=f"scripted attempt {a.tactic}",
                    steps=(AuditStep(label="reasoning", detail={"why": "test double"}),),
                ),
            )
            for a in self.attempts
            if a.white_box == white_box
        ]
