"""Adversary port: proposes a label-preserving mutation of a task.

Given a task the victim CAUGHT (its gate ``score`` is at/above threshold) the
adversary returns a mutated task that the victim is expected to clear while the
task's true intent is preserved — or ``None`` if it finds none. ``task`` is
opaque: a transaction for the fraud victim, a code spec / framing for a
produce-victim (code agent). The harness re-evaluates every proposal against the
real victim + label authority (it never trusts the adversary's word), so the
signature is the same for both victim shapes.
"""

from typing import Protocol


class Adversary(Protocol):
    def mutate(self, sample: object, score: float) -> object | None: ...
