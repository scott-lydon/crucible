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
    UniqueConstraint,
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


class StrategyCatalogEntry(Base):
    """A successful evasion tactic: the red pillar's institutional memory (US-6).

    No foreign key to runs on purpose: the catalog is a reusable benchmark that
    outlives any single run (proposal section 3, Pillar 4), so a tactic stays
    even if its discovering run is later pruned. One row per (tactic,
    target_type); rediscovery increments reuse_count and adds to total_dollars,
    so average dollars-to-succeed is total_dollars / reuse_count.
    """

    __tablename__ = "strategy_catalog"
    __table_args__ = (
        UniqueConstraint("tactic", "target_type", name="uq_strategy_tactic_target"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tactic: Mapped[str] = mapped_column(String(256), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    first_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reuse_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_dollars: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    prompt_fragment: Mapped[str] = mapped_column(Text, nullable=False)
    discovery_audit: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MetamorphicRule(Base):
    """One metamorphic relation synthesized from the sealed spec's invariants.

    A relation is a property that must hold when an input is transformed, with
    no reference answer needed. Persisted so the verdict view can render which
    relations fired.
    """

    __tablename__ = "metamorphic_rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    spec_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_code: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BluePatch(Base):
    """One blue-loop hardening proposal, pending held-out validation (US-7).

    `kind` is "retrain" for a Shape-1 target (a new LightGBM artifact) or
    "prompt_config" for a Shape-2 target (an agent-config diff). `detail` carries
    the proposed features / adversarial samples / diff, and `provenance` the
    catalog attack ids the proposal was built from, so the held-out validator can
    refuse a contaminated set (US-7).
    """

    __tablename__ = "blue_patches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    pillar: Mapped[str] = mapped_column(String(16), nullable=False, default="blue")
    dollars_spent: Mapped[Decimal] = mapped_column(_MONEY, nullable=False, default=Decimal("0"))
    seed: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audit_trace: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AgentConfig(Base):
    """A versioned prompt-and-configuration for the code-agent target.

    The vendor language model is never modified; hardening the code agent means
    a new system-prompt-and-config row at the next version integer (US-7,
    ARCHITECTURE.md section 3, Pillar 3).
    """

    __tablename__ = "agent_configs"
    __table_args__ = (UniqueConstraint("version", name="uq_agent_config_version"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("blue_patches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ModelVersion(Base):
    """One hardened target version, recording both shapes under one schema.

    For the fraud target `artifact_ref` is the new `.lgb` path at the next
    version integer; for the code agent it is the agent-config row id. `metrics`
    carries the held-out detection figures the patch was validated on.
    """

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("target_type", "version", name="uq_model_version_target"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    artifact_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    patch_id: Mapped[str | None] = mapped_column(ForeignKey("blue_patches.id"), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HoldoutRun(Base):
    """One held-out validation of a blue patch (US-7).

    Records detection rate before and after the patch on an up-front held-out
    attack set that never overlaps the patch's training attacks (the validator
    refuses on contamination). `recovered` is the honest verdict, including a
    real "did not generalize" when after does not exceed before.
    """

    __tablename__ = "holdout_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patch_id: Mapped[str] = mapped_column(ForeignKey("blue_patches.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    holdout_size: Mapped[int] = mapped_column(Integer, nullable=False)
    detection_before: Mapped[float] = mapped_column(Float, nullable=False)
    detection_after: Mapped[float] = mapped_column(Float, nullable=False)
    recovered: Mapped[bool] = mapped_column(Boolean, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    seed: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# The per-oracle detail tables the slice-10 reconciliation deferred until a
# renderer existed (this slice is that renderer). Each is one row per relevant
# oracle vote on a verdict; the aggregated `verdicts.votes` stays the single
# tally source, while these carry the oracle-specific drill-down the verdict view
# expands. Detail the oracle reports beyond the vote rides `detail` / `reason`.


class JudgeVote(Base):
    """The LLM judge's half-weight vote behind a verdict (US-4 card)."""

    __tablename__ = "judge_votes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    verdict_id: Mapped[str] = mapped_column(ForeignKey("verdicts.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FuzzFinding(Base):
    """One property-fuzz outcome behind a verdict: the decision and counterexample."""

    __tablename__ = "fuzz_findings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    verdict_id: Mapped[str] = mapped_column(ForeignKey("verdicts.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    counterexample: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DifferentialRun(Base):
    """One differential-oracle comparison behind a verdict: the disagreement detail."""

    __tablename__ = "differential_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    verdict_id: Mapped[str] = mapped_column(ForeignKey("verdicts.id"), nullable=False)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class HaltState(Base):
    """The certification halt flag the orchestrator checks before a launch (US-13).

    A single row keyed `global`: when white-box verifier recall falls below the
    configured red line, `halted` is set true and the orchestrator refuses new
    run launches with HTTP 409. Persisted (not just computed) so the flag is the
    auditable record of when and why certification was halted.
    """

    __tablename__ = "halt_state"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    halted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkspacePolicy(Base):
    """The workspace's governance policy (slice-15, C12).

    Stores the operative policy as a YAML/text document. Single-workspace today,
    so a single row keyed ``global``; the route falls back to the real
    config-derived halt policy when no custom policy has been stored, so /policy
    is never empty on a fresh deployment.
    """

    __tablename__ = "workspace_policy"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    policy_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RunOverride(Base):
    """An admin override action, append-only audit log (slice-12, C9).

    Each row records one override the admin debug panel applied to a run (a
    dev-mode toggle, a forced status), so the audit log the panel renders is real
    and empty on a fresh deployment rather than the design bundle's hardcoded
    entries.
    """

    __tablename__ = "run_overrides"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False, default="anonymous")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
