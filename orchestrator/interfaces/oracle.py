from typing import Protocol
from shared.types import VerdictContext, OracleVote, OracleKind

class Oracle(Protocol):
    """Judges one victim decision. ``ctx`` carries the task (``ctx.sample``), the
    produced output (``ctx.output`` for a produce-victim; ``None`` for the fraud
    classifier whose output is ``ctx.detector_score``) and the sealed ``ctx.spec``
    — so the same oracle protocol serves both classify and produce victims."""

    @property
    def kind(self) -> OracleKind: ...
    def vote(self, ctx: VerdictContext) -> OracleVote: ...
    def describe(self) -> str:
        """A short, generic protocol description (the MECHANISM, not target
        specifics). Used to assemble the verification scheme for the white-box
        red pass (US-14)."""
        ...
