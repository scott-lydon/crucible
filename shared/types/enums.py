"""Closed enumerations shared across pillars. String-valued so they persist and
serialize without adapters. Term referents are pinned in docs/VOCABULARY.md."""

from __future__ import annotations

from enum import StrEnum


class Pillar(StrEnum):
    """The owning pillar of a persisted row (per plan.md section 7)."""

    targets = "targets"
    oracles = "oracles"
    red = "red"
    blue = "blue"
    measure = "measure"
    orchestrator = "orchestrator"


class Shape(StrEnum):
    """Target architecture shape (VOCABULARY.md: Shape 1 / Shape 2)."""

    shape1_ml = "shape1_ml"        # custom ML model the customer owns (fraud LightGBM)
    shape2_agent = "shape2_agent"  # agent product on a vendor LLM (code agent)


class OracleKind(StrEnum):
    """The five verifiers. The first four carry one vote; the judge carries half."""

    held_out = "held_out"
    metamorphic = "metamorphic"
    differential = "differential"
    property_fuzz = "property_fuzz"
    llm_judge = "llm_judge"


class VerdictOutcome(StrEnum):
    """A single verdict's conclusion about one producer output."""

    clean = "clean"    # insufficient evidence of producer wrongness
    caught = "caught"  # the ensemble caught producer wrongness


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"
    halted = "halted"
