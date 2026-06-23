from dataclasses import dataclass
from shared.types.enums import OracleKind, Vote
from shared.types.sealed_spec import SealedSpec

@dataclass(frozen=True, slots=True)
class VerdictContext:
    sample: object
    detector_score: float
    threshold: float
    true_label: bool
    original_sample: object | None
    original_score: float | None
    spec: SealedSpec

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
