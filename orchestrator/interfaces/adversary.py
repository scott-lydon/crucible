from typing import Protocol
from shared.types import Transaction

class Adversary(Protocol):
    def mutate(self, txn: Transaction, score: float) -> Transaction | None: ...
