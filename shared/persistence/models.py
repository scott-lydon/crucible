from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

class SpecRow(Base):
    """The sealed spec for a run, stored server-side.

    The producer (sandboxed target code) is NEVER given DB creds or this row's
    contents — only its input sample. The harness/oracles resolve the spec
    server-side (in-process, with the app's DB creds) via the repo resolver.
    Dialect-neutral: the serialized SealedSpec lives in a generic JSON column.
    """

    __tablename__ = "specs"
    spec_id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    spec_json: Mapped[dict[str, object]] = mapped_column(JSON)
    pillar: Mapped[str] = mapped_column(String, default="orchestrator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RunRow(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    seed: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    n_rounds: Mapped[int] = mapped_column(Integer)
    batch_size: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[float] = mapped_column(Float)
    params_json: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    pillar: Mapped[str] = mapped_column(String, default="orchestrator")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class RoundRow(Base):
    __tablename__ = "rounds"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_index: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class TransactionRow(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"))
    txn_index: Mapped[int] = mapped_column(Integer)
    features_json: Mapped[dict[str, object]] = mapped_column(JSON)
    true_label: Mapped[bool] = mapped_column(Boolean)
    origin: Mapped[str] = mapped_column(String)
    txn_slice: Mapped[str] = mapped_column(String)
    parent_txn_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detector_score: Mapped[float] = mapped_column(Float)
    caught: Mapped[bool] = mapped_column(Boolean)
    seed: Mapped[str] = mapped_column(String)
    pillar: Mapped[str] = mapped_column(String, default="targets")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class AttackRow(Base):
    __tablename__ = "attacks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"))
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    parent_txn_id: Mapped[str] = mapped_column(String)
    mutation_json: Mapped[dict[str, object]] = mapped_column(JSON)
    pre_score: Mapped[float] = mapped_column(Float)
    post_score: Mapped[float] = mapped_column(Float)
    evaded: Mapped[bool] = mapped_column(Boolean)
    true_label_preserved: Mapped[bool] = mapped_column(Boolean)
    seed: Mapped[str] = mapped_column(String)
    pillar: Mapped[str] = mapped_column(String, default="red")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class VerdictRow(Base):
    __tablename__ = "verdicts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    round_id: Mapped[str] = mapped_column(ForeignKey("rounds.id"))
    txn_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"))
    aggregate_pass: Mapped[bool] = mapped_column(Boolean)
    fail_weight: Mapped[float] = mapped_column(Float)
    pass_weight: Mapped[float] = mapped_column(Float)
    audit_trace_json: Mapped[dict[str, object]] = mapped_column(JSON)
    seed: Mapped[str] = mapped_column(String)
    pillar: Mapped[str] = mapped_column(String, default="oracles")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class OracleVoteRow(Base):
    __tablename__ = "oracle_votes"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    verdict_id: Mapped[str] = mapped_column(ForeignKey("verdicts.id"))
    oracle_kind: Mapped[str] = mapped_column(String)
    vote: Mapped[str] = mapped_column(String)
    weight: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class WhiteBoxMetricsRow(Base):
    """Black-box vs white-box catch rate + the gap for a run (US-14 / slice-12).

    Keyed to the BLACK-BOX run. The white-box pass runs as a SEPARATE run; its
    id is recorded here so the two passes are auditable. ``white_box_gap`` =
    ``black_box_catch_rate - white_box_catch_rate`` (an informed attacker is
    caught no more often than an ignorant one, so the gap is >= 0 on a sane run).
    Rates are nullable: a pass with no successful evasions has an undefined
    catch rate, never a misleading zero.
    """

    __tablename__ = "white_box_metrics"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    white_box_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    black_box_catch_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    white_box_catch_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    white_box_gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    pillar: Mapped[str] = mapped_column(String, default="measure")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class HaltStateRow(Base):
    """The platform's certification halt flag (US-13 / slice-18).

    A single-row table (``id == "singleton"``) that survives restarts: when the
    latest white-box verifier recall drops below the configured red line, the
    platform is HALTED and new run launches are refused. The recall + threshold
    that triggered the halt are recorded alongside the flag so the dashboard
    banner and the 409 error body can report the exact numbers. Rates are
    nullable so an un-halted (or never-measured) state is honest, not a fake 0.
    """

    __tablename__ = "halt_state"
    id: Mapped[str] = mapped_column(String, primary_key=True, default="singleton")
    halted: Mapped[bool] = mapped_column(Boolean, default=False)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pillar: Mapped[str] = mapped_column(String, default="measure")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LlmCallRow(Base):
    """One recorded LLM completion (US-2/US-3 Inspect + US-10 cost).

    Written by ``shared.llm.persisting.PersistingLLMProvider`` AROUND each real
    provider call — it RECORDS the call already happening, it never makes a new
    one. ``pillar`` names the call site (``judge``/``red``/``blue``/``white_box``)
    so the dashboard can group cost by pillar. ``prompt``/``system`` are the exact
    inputs; ``raw_response`` is the provider's raw payload (JSON-serialized text);
    ``parsed_output`` is the caller-side parse when known (left null here — the
    wrapper records the response verbatim, parsing is the caller's concern). The
    token + ``dollars`` fields mirror ``LLMResponse`` so cost is HONEST per model.
    """

    __tablename__ = "llm_calls"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    pillar: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(String)
    system: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_response: Mapped[str | None] = mapped_column(String, nullable=True)
    parsed_output: Mapped[str | None] = mapped_column(String, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    dollars: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BlueRoundRow(Base):
    """One blue recovery round: the defender's propose->retrain->validate arc."""

    __tablename__ = "blue_rounds"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    features_added: Mapped[list[str]] = mapped_column(JSON)
    detection_before: Mapped[float] = mapped_column(Float)
    detection_after: Mapped[float] = mapped_column(Float)
    recovered: Mapped[float] = mapped_column(Float)
    n_holdout: Mapped[int] = mapped_column(Integer)
    proposer_rationale: Mapped[str] = mapped_column(String)
    new_model_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    # The full Option-B iteration trail: one entry per propose->sandbox->retrain
    # ->validate attempt (rationale, engineered code, sandbox_ok, recovered).
    iteration_trail: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    pillar: Mapped[str] = mapped_column(String, default="blue")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
