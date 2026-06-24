"""Verdict and OracleVote value objects.

A Verdict is the aggregated call over one submission. Each OracleVote keeps
its own reasoning so "the LLM judge alone" can never be mistaken for "the
verdict" (US-4). The aggregation rule (four oracles at weight 1, judge at
0.5, pass threshold 2.0) lives in the oracles module's aggregator, landing
in slice 10; this file is only the data shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from .audit import AuditTrace
from .enums import VerdictDecision
from .ids import AttackId, RunId, VerdictId


@dataclass(frozen=True, slots=True)
class OracleVote:
    """One oracle's call on one submission, with its reasoning attached."""

    oracle_name: str
    decision: VerdictDecision
    weight: float
    reason: str
    obligation_id: str | None = None

    def __post_init__(self) -> None:
        if self.weight < 0:
            raise ValueError(
                f"OracleVote.weight must be non-negative; got {self.weight} "
                f"for oracle {self.oracle_name!r}."
            )


@dataclass(frozen=True, slots=True)
class Verdict:
    """The aggregated outcome over one submission."""

    verdict_id: VerdictId
    run_id: RunId
    attack_id: AttackId | None
    votes: tuple[OracleVote, ...]
    passed: bool
    tally: float
    audit: AuditTrace
