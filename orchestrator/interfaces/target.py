"""Target ports: the victim under test.

Two shapes of the SAME idea — a victim that, given a TASK, PRODUCES an OUTPUT
the oracles then judge:

- ``Producer.produce(task) -> output``  — the general shape. ``task`` and
  ``output`` are opaque to the harness: for a code-generation victim the task is
  a sealed code spec and the output is produced source; for the fraud victim the
  task is a transaction and the output IS its fraud score (a degenerate producer
  whose output already is the judged artifact).

- ``Detector.score(sample) -> float`` — the classifier shape, kept verbatim for
  the existing fraud path. A ``Detector`` IS a ``Producer`` whose ``produce`` is
  ``score`` and whose output is the float score; ``score`` is retained as the
  canonical name the fraud loop/oracles/adversary already call, so fraud
  behavior is byte-identical. New produce-victims implement ``Producer.produce``.

Both protocols are structural (``Protocol``) and opaque: the harness hardcodes no
fraud- or code-specific knowledge. A produce-victim must additionally arrange for
its oracles to judge the produced ``output`` (carried generically on
``VerdictContext.output``) against its sealed spec — see ``shared/types/verdict.py``.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The result of running the victim on one task: what it PRODUCED, a scalar
    the loop compares to ``threshold`` to decide "caught", and the produced
    artifact for the oracles.

    For the fraud classifier (degenerate producer) ``score`` IS the produced
    output and ``output`` is ``None`` — keeping the persisted row + every fraud
    oracle's view byte-identical. A produce-victim returns its produced artifact
    in ``output`` and a scalar gate in ``score`` (e.g. 0.0 vs a 0.5 threshold to
    always route through the oracle verdict path).

    Lives in ``interfaces`` (alongside ``Producer``) so an ``examples/`` victim's
    ``TargetEngine`` can construct it without importing ``orchestrator.loop`` —
    examples may only see ``orchestrator.interfaces`` + ``shared.*``.
    """

    score: float
    output: object | None


class TargetEngine(Protocol):
    """The target-shaped seam the generic loop delegates to.

    The loop owns persistence, slicing, the adversary call and the oracle
    aggregation — all victim-agnostic. Everything that depends on whether the
    victim CLASSIFIES or PRODUCES is isolated behind this protocol, so a
    produce-victim (code agent) drives the SAME loop by supplying a different
    engine. ``ClassifyEngine`` (in ``orchestrator.loop``) is the fraud adapter.
    """

    def evaluate(self, task: object) -> "Evaluation":
        """Run the victim on ``task``; return its produced output + gate score."""
        ...


class Producer(Protocol):
    """A victim that produces an output from a task. The general target shape.

    ``task`` and the returned output are opaque ``object``s — the harness moves
    them around without inspecting their type. A produce-victim's oracles read
    the output (via ``VerdictContext.output``) and the task (via
    ``VerdictContext.sample``) plus the sealed spec to render a verdict.
    """

    def produce(self, task: object) -> object: ...


class Detector(Protocol):
    """The classifier-shaped target (the fraud path), kept verbatim.

    A ``Detector`` is the degenerate ``Producer`` whose produced output IS its
    score; the fraud loop/oracles/adversary call ``score`` directly, so this name
    is preserved unchanged to keep fraud behavior byte-identical.
    """

    def score(self, sample: object) -> float: ...
