from dataclasses import dataclass
from shared.types.enums import OracleKind, Vote
from shared.types.sealed_spec import SealedSpec

@dataclass(frozen=True, slots=True)
class VerdictContext:
    """What an oracle judges: a victim's decision about one task.

    The fields model the GENERAL produce shape — a victim was given a TASK
    (``sample``) and PRODUCED an OUTPUT (``output``) the oracles assess against
    the sealed ``spec``. For the fraud (classifier) victim the produced output IS
    the score, so ``detector_score`` carries it and ``output`` defaults to
    ``None`` — leaving every existing fraud oracle's view byte-identical. A
    produce-victim (e.g. a code agent) sets ``output`` to its produced artifact
    (e.g. source code) and its oracles read ``output`` + ``sample`` + ``spec``.

    ``detector_score``/``threshold`` stay first-class for the fraud oracles that
    compare score-vs-threshold; a pure produce-victim whose verdict is not a
    threshold crossing passes ``detector_score=0.0`` (or any sentinel its oracles
    ignore) and judges ``output`` directly.
    """

    sample: object
    detector_score: float
    threshold: float
    true_label: bool
    original_sample: object | None
    original_score: float | None
    spec: SealedSpec
    # The produced artifact for a produce-victim (code agent). ``None`` for the
    # fraud classifier, whose produced output is the score in ``detector_score``.
    output: object | None = None

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
