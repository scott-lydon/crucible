from collections.abc import Callable
from dataclasses import replace
from shared.types import Transaction


class AmountLoweringAdversary:
    """Lowers `amount` toward the detector's blind spot while preserving the
    true fraud label. Returns None if no evading-yet-still-fraud variant exists."""

    def __init__(self, score_fn: Callable[[Transaction], float],
                 label_fn: Callable[[Transaction], bool], threshold: float) -> None:
        self._score = score_fn
        self._is_fraud = label_fn
        self._threshold = threshold

    def mutate(self, txn: Transaction, score: float) -> Transaction | None:
        # Search a deterministic descending ladder of amounts.
        for factor in (0.5, 0.25, 0.1, 0.05, 0.02):
            candidate = replace(txn, amount=round(txn.amount * factor, 2))
            if not self._is_fraud(candidate):
                continue                       # would flip the label -> reject
            if self._score(candidate) < self._threshold:
                return candidate               # evades AND still fraud
        return None
