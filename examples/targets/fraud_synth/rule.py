from typing import cast
from examples.targets.fraud_synth.transaction import Transaction
from examples.targets.fraud_synth.constants import V_THRESH, A_HIGH, MERCHANT_RISK_HIGH


def is_fraud(sample: object) -> bool:
    txn = cast(Transaction, sample)
    return (txn.velocity > V_THRESH
            or txn.country_mismatch
            or (txn.amount > A_HIGH and txn.merchant_risk > MERCHANT_RISK_HIGH))
