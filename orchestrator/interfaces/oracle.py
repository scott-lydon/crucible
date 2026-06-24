from typing import Protocol
from shared.types import VerdictContext, OracleVote, OracleKind

class Oracle(Protocol):
    @property
    def kind(self) -> OracleKind: ...
    def vote(self, ctx: VerdictContext) -> OracleVote: ...
    def describe(self) -> str:
        """A short, generic protocol description (the MECHANISM, not target
        specifics). Used to assemble the verification scheme for the white-box
        red pass (US-14)."""
        ...
