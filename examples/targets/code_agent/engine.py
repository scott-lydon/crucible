"""The ``TargetEngine`` for the code-agent victim (the produce shape).

``CodeAgentEngine.evaluate(task)`` runs the producer and returns
``Evaluation(score=0.0, output=<produced source>)``. The gate score is fixed at
0.0 (< any positive threshold), so EVERY task routes through the loop's oracle
verdict path — the produce shape has no "caught" notion; the produced artifact is
judged by the held-out-test oracle reading ``ctx.output``.

This satisfies the Step-0 producer contract: the engine is the seam the generic
``run_loop`` delegates to, isolating the produce-vs-classify decision from the
target-agnostic loop.
"""

from __future__ import annotations

from examples.targets.code_agent.producer import CodeAgentProducer
from orchestrator.interfaces import Evaluation

# Any positive threshold beats this gate, so produce-victim tasks are never
# "caught" — they all route to the oracle verdict path. Single source of truth
# for the gate value so the engine and any test agree.
_GATE_SCORE = 0.0


class CodeAgentEngine:
    """``TargetEngine`` wrapping a ``CodeAgentProducer`` (the code-agent victim)."""

    def __init__(self, producer: CodeAgentProducer) -> None:
        self._producer = producer

    def evaluate(self, task: object) -> Evaluation:
        return Evaluation(score=_GATE_SCORE, output=self._producer.produce(task))
