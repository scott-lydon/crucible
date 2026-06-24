from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def _now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    pass

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
