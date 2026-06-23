from typing import Protocol
from shared.types import VerdictContext, OracleVote, OracleKind

class Oracle(Protocol):
    @property
    def kind(self) -> OracleKind: ...
    def vote(self, ctx: VerdictContext) -> OracleVote: ...
