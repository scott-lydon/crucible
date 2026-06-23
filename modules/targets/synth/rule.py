from shared.types import Transaction
from modules.targets.synth.constants import V_THRESH, A_HIGH, MERCHANT_RISK_HIGH


def is_fraud(txn: Transaction) -> bool:
    return (txn.velocity > V_THRESH
            or txn.country_mismatch
            or (txn.amount > A_HIGH and txn.merchant_risk > MERCHANT_RISK_HIGH))
