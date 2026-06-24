"""ORM models for the slice-0 schema.

Every work-done row carries the transparency columns from ARCHITECTURE.md
section 7: created_at, pillar, dollars_spent, seed, audit_trace, and where a
replay chain exists, parent_action_id. Migrations in
shared/persistence/migrations/versions/ are the source of truth for the live
schema; these classes are the source of truth those migrations are generated
from.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

# Numeric precision for every dollar column: up to 999999.999999.
_MONEY = Numeric(12, 6)


class Run(Base):
    """One red-and-blue pass over a target."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    spec_title: Mapped[str] = mapped_column(String(512), nullable=False)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    budget_max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_max_dollars: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    seed: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Attack(Base):
    """One red-agent attempt against the target."""

    __tablename__ = "attacks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    tactic: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    white_box: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hybrid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pillar: Mapped[str] = mapped_column(String(16), nullable=False, default="red")
    dollars_spent: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    seed: Mapped[str] = mapped_column(Text, nullable=False)
    audit_trace: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Verdict(Base):
    """The aggregated oracle outcome over one submission."""

    __tablename__ = "verdicts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    attack_id: Mapped[str | None] = mapped_column(ForeignKey("attacks.id"), nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tally: Mapped[float] = mapped_column(Float, nullable=False)
    votes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    pillar: Mapped[str] = mapped_column(String(16), nullable=False, default="oracles")
    dollars_spent: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    seed: Mapped[str] = mapped_column(Text, nullable=False)
    audit_trace: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LlmCall(Base):
    """One large-language-model call, surfaced as the dashboard trace card."""

    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pillar: Mapped[str] = mapped_column(String(16), nullable=False)
    dollars_spent: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    seed: Mapped[str] = mapped_column(Text, nullable=False)
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SandboxJob(Base):
    """One Modal producer-sandbox execution, with its seal evidence."""

    __tablename__ = "sandbox_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    modal_job_id: Mapped[str] = mapped_column(String(128), nullable=False)
    env_applied: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    network_rules: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=False)
    stdout: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stderr: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seed: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HealthProbe(Base):
    """The latest self-test result for one subcomponent (US-8)."""

    __tablename__ = "health_probes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pillar: Mapped[str] = mapped_column(String(16), nullable=False)
    subcomponent: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_self_test_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Spec(Base):
    """A sealed specification, stored server-side.

    The producer sandbox has no network and so cannot read this table; oracles
    read it through SpecResolver. The whole spec is stored as its `as_json`
    form so the row round-trips back to a SealedSpec with its id intact.
    """

    __tablename__ = "specs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    spec_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HeldOutTest(Base):
    """A test generated after submission by the held-out oracle.

    Never exposed to the producer (which is sealed) and deleted after the run
    completes, so a static held-out set cannot leak across runs.
    """

    __tablename__ = "held_out_tests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    spec_id: Mapped[str] = mapped_column(String(64), nullable=False)
    test_code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
