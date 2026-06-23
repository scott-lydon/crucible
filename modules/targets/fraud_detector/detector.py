import math
from shared.types import Transaction
from modules.targets.synth.constants import AMOUNT_SCALE


class FlawedDetector:
    """Mostly amount-weighted logistic scorer. Over-relies on the easiest
    visible proxy (amount) and underweights the true causal signals."""

    BIAS = 2.4  # tuned so high-amount -> >=0.5, low-amount -> <0.5

    def score(self, txn: Transaction) -> float:
        z = (2.8 * (txn.amount / AMOUNT_SCALE)
             + 0.15 * txn.merchant_risk
             + 0.05 * txn.velocity
             + 0.03 * (1.0 if txn.country_mismatch else 0.0)
             - self.BIAS)
        return 1.0 / (1.0 + math.exp(-z))
