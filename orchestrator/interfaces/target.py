from typing import Protocol
from shared.types import Transaction

class Detector(Protocol):
    def score(self, txn: Transaction) -> float: ...
