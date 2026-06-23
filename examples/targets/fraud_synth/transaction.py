from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Transaction:
    txn_index: int
    amount: float
    velocity: int
    country_mismatch: bool
    merchant_risk: float
    hour_of_day: int
