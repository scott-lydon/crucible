"""Closed-set enumerations persisted to Postgres and serialized to JSON.

These are backed string enums (StrEnum) because each value is stored in the
database and crosses the API boundary, per coding-practices.md section on
"Enums over constants".
"""

from __future__ import annotations

from enum import StrEnum


class Pillar(StrEnum):
    """Which ownership boundary produced a persisted row.

    Every work-done row carries one of these in its `pillar` column for cost
    attribution and transparency (coding-practices.md section 3).
    """

    TARGETS = "targets"
    ORACLES = "oracles"
    RED = "red"
    BLUE = "blue"
    MEASURE = "measure"
    ORCHESTRATOR = "orchestrator"


class RunStatus(StrEnum):
    """Lifecycle of a single red-and-blue pass over a target."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    HALTED = "halted"
    FAILED = "failed"


class TargetType(StrEnum):
    """Which target adapter a run drives.

    `research_agent` ships as a stub the orchestrator skips at runtime
    (ARCHITECTURE.md section 12). `dummy` exists only for the slice-1 loop
    smoke test.
    """

    FRAUD = "fraud"
    CODE_AGENT = "code_agent"
    RESEARCH_AGENT = "research_agent"
    DUMMY = "dummy"


class ProbeStatus(StrEnum):
    """Self-test status for one subcomponent on the /health page (US-8)."""

    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class VerdictDecision(StrEnum):
    """One oracle's call on one submission.

    `unavailable` is a real, recorded outcome (the oracle's LLM call timed
    out, for example), never a guess. The aggregator reports on the remaining
    votes rather than inventing one (ARCHITECTURE.md section 3 failure modes).
    """

    PASS = "pass"
    FAIL = "fail"
    UNAVAILABLE = "unavailable"
