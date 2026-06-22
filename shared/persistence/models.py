"""ORM rows. These are the persistence projection of the domain types in
shared/types/. Slice 0 lands the core loop tables (runs, specs, attacks, verdicts,
llm_calls, sandbox_jobs, health_probes); later slices add their own tables through
additive Alembic migrations."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from shared.persistence.base import AuditMixin, Base


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    shape: Mapped[str] = mapped_column(String(20), nullable=False)
    budget_rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    budget_dollars: Mapped[float] = mapped_column(Float, nullable=False)
    dollars_spent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    halted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    white_box_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SpecRow(Base):
    """The sealed spec, read by oracles through a server-side resolver the producer
    container cannot reach (constitution.md section 3)."""

    __tablename__ = "specs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    shape: Mapped[str] = mapped_column(String(20), nullable=False)
    holdout_generator_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class AttackRow(AuditMixin, Base):
    __tablename__ = "attacks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tactic: Mapped[str] = mapped_column(String(120), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    white_box: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hybrid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class VerdictRow(AuditMixin, Base):
    __tablename__ = "verdicts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    attack_id: Mapped[str] = mapped_column(ForeignKey("attacks.id"), nullable=False, index=True)
    producer_output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    votes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    tally: Mapped[float] = mapped_column(Float, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)


class LLMCallRow(Base):
    """One Anthropic call, with its full trace surface (constitution.md section 4)."""

    __tablename__ = "llm_calls"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), nullable=True, index=True)
    pillar: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dollars: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    seed: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    parent_action_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SandboxJobRow(Base):
    """One producer sandbox execution (constitution.md section 4; spec US-9)."""

    __tablename__ = "sandbox_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("runs.id"), nullable=True, index=True)
    pillar: Mapped[str] = mapped_column(String(20), nullable=False, default="targets")
    job_ref: Mapped[str] = mapped_column(String(120), nullable=False)
    env_applied: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    network_rules: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    exit_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stdout: Mapped[str] = mapped_column(Text, nullable=False, default="")
    stderr: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seed: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class HealthProbeRow(Base):
    """Last self-test result for one subcomponent (spec US-8)."""

    __tablename__ = "health_probes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pillar: Mapped[str] = mapped_column(String(20), nullable=False)
    module: Mapped[str] = mapped_column(String(60), nullable=False)
    subcomponent: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # green|amber|red
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=False
    )
