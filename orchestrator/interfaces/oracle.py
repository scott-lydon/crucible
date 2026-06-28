"""The Oracle port. Each of the five verifiers implements this. An oracle votes on
whether one producer output violates the sealed spec; it never sees the other
oracles' votes (non-colluding ensemble, plan.md section 5)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from shared.types.core import Attack, OracleVote, Verdict
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus, ProducerResult
from shared.types.sealed_spec import SealedSpec

# Re-submit one input to the producer (used by the metamorphic oracle to re-query under
# paraphrases). The loop binds this to the RUN's actual target so it grades the agent
# under test, not a default (cr-ui3).
ResubmitFn = Callable[[Mapping[str, Any]], Awaitable[ProducerResult]]


@runtime_checkable
class Oracle(Protocol):
    # Read-only: an oracle's identity (kind) and vote weight are constant for its lifetime.
    # Declaring them as properties (not settable attributes) lets a frozen-dataclass oracle
    # like LLMJudgeOracle satisfy the protocol while plain-class oracles still match
    # (PR3 port A1: module value objects are frozen).
    @property
    def kind(self) -> OracleKind: ...

    @property
    def weight(self) -> float:  # 1.0 for the four independent oracles, 0.5 for the judge
        ...

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        """Check one producer output against the spec and return a reasoned vote."""
        ...

    async def health(self) -> HealthStatus: ...


@runtime_checkable
class Retargetable(Protocol):
    """An oracle that re-queries the producer and must be pointed at the run's target."""

    def set_resubmit(self, resubmit: ResubmitFn) -> None: ...


class VerifyFn(Protocol):
    """The aggregator, injected into the loop by wiring so loop.py never imports a
    concrete module (constitution.md section 2). Polls the oracles and aggregates."""

    async def __call__(
        self,
        oracles: Sequence[Oracle],
        spec: SealedSpec,
        attack: Attack,
        output: Mapping[str, Any],
    ) -> Verdict: ...
