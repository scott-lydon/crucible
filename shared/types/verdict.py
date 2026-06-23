from dataclasses import dataclass
from shared.types.transaction import Transaction
from shared.types.enums import OracleKind, Vote

@dataclass(frozen=True, slots=True)
class VerdictContext:
    txn: Transaction
    detector_score: float
    threshold: float
    true_label: bool
    original_txn: Transaction | None
    original_score: float | None

@dataclass(frozen=True, slots=True)
class OracleVote:
    kind: OracleKind
    vote: Vote
    weight: float
    reason: str
    evidence: dict[str, object]

@dataclass(frozen=True, slots=True)
class Verdict:
    aggregate_pass: bool
    fail_weight: float
    pass_weight: float
    votes: tuple[OracleVote, ...]
    tally: dict[str, object]
