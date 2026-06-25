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

from typing import Protocol


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
