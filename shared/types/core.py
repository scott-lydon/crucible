"""Core in-memory value objects passed across interface boundaries.

These are distinct from the SQLAlchemy ORM rows in shared/persistence/models.py:
the orchestrator and modules speak in these frozen dataclasses; persistence maps
them to and from rows. Keeping the two separate is what lets modules stay ignorant
of the database (constitution.md section 2)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from shared.types.enums import OracleKind, Pillar, VerdictOutcome
from shared.types.ids import AttackId, RunId, VerdictId


@dataclass(frozen=True, slots=True)
class AttackBudget:
    """The ceiling an operator sets on a run (spec.md US-1)."""

    max_rounds: int
    max_dollars: float


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """What the orchestrator needs to launch a target (spec.md US-1)."""

    target_kind: str        # "fraud" | "code_agent" | "dummy"
    shape: str              # Shape value
    artifact_ref: str       # .lgb checksum (Shape 1) or agent-config version (Shape 2)


@dataclass(frozen=True, slots=True)
class Attack:
    """One adversarial input the red agent fed to the producer."""

    attack_id: AttackId
    run_id: RunId
    round_index: int
    tactic: str
    payload: Mapping[str, Any]   # the producer input (e.g. a transaction record)
    rationale: str
    seed: str
    white_box: bool = False
    hybrid: bool = False
    # Oracle-side context the producer NEVER sees (the target is given only `payload`).
    # The held-out oracle reads the ground-truth label from here.
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class OracleVote:
    """One oracle's reasoned vote on one producer output.

    ``fired`` True means the oracle asserts producer wrongness. ``weight`` is 1.0
    for the four independent oracles and 0.5 for the LLM judge (plan.md section 3).
    """

    oracle: OracleKind
    fired: bool
    weight: float
    obligation: str       # the spec obligation checked, verbatim
    observation: str      # what the oracle observed
    reason: str           # one-paragraph reason (never swallowed — QA_ADVERSARY rule 3)
    seed: str
    dollars: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serializable form for the verdict audit trace (persisted to JSONB)."""
        return {
            "oracle": str(self.oracle),
            "fired": self.fired,
            "weight": self.weight,
            "obligation": self.obligation,
            "observation": self.observation,
            "reason": self.reason,
            "dollars": self.dollars,
            "seed": self.seed,
        }


@dataclass(frozen=True, slots=True)
class AuditTrace:
    """The full reasoning surface persisted on a row (constitution.md section 4)."""

    pillar: Pillar
    summary: str
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Verdict:
    """The aggregated conclusion of the oracle ensemble on one producer output."""

    verdict_id: VerdictId
    run_id: RunId
    attack_id: AttackId
    producer_output: Mapping[str, Any]
    votes: tuple[OracleVote, ...]
    tally: float          # sum of weights of oracles that fired
    threshold: float      # caught iff tally >= threshold (default 2.0)
    outcome: VerdictOutcome
    audit: AuditTrace
    seed: str
    dollars: float = 0.0

    @property
    def caught(self) -> bool:
        return self.outcome is VerdictOutcome.caught
