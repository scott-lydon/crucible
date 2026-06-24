from shared.types import VerdictContext, OracleVote, OracleKind, Vote
from orchestrator.interfaces import Detector, Adversary, Oracle
from examples.targets.fraud_synth import Transaction


class _Det:
    def score(self, sample: object) -> float:
        return 0.0

class _Adv:
    def mutate(self, sample: object, score: float) -> object | None:
        return None

class _Ora:
    @property
    def kind(self) -> OracleKind:
        return OracleKind.INVARIANT

    def vote(self, ctx: VerdictContext) -> OracleVote:
        return OracleVote(self.kind, Vote.PASS, 1.0, "ok", {})

    def describe(self) -> str:
        return "stub oracle"

def test_stubs_satisfy_protocols() -> None:
    d: Detector = _Det()
    a: Adversary = _Adv()
    o: Oracle = _Ora()
    assert d.score(Transaction(0, 1.0, 1, False, 0.1, 9)) == 0.0
    assert a.mutate(Transaction(0, 1.0, 1, False, 0.1, 9), 0.9) is None
    assert o.kind is OracleKind.INVARIANT
