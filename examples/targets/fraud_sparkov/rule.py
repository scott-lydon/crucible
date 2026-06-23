"""The DECLARED ground-truth fraud rule over interpretable features.

This is the sealed oracle's ground truth AND the red loop's ``label_fn``. It is
derived from the Step-1 analysis of the REAL data and labels 95.3% of the real
``is_fraud`` rows as fraud (recall vs the real labels; see the build report).

CAVEAT: this rule is a DELIBERATELY SIMPLIFIED ground-truth PROXY — high recall
(~95%) but low precision (~2%): it over-flags night-hour transactions. The
co-evolution gap measures recall loss against THIS declared spec, not catch
rate against real fraud. See README.md (an instance of Crucible's "the spec is
a proxy for intent; surface the residual" thesis).

Design intent for the metamorphic relation: a transaction is fraud if it occurs
in the night window REGARDLESS of amount. So lowering ``amt`` on a night-fraud
preserves the fraud label, while the amount-reliant flawed detector clears it —
a real, non-fabricated amt-lowering evasion.
"""

from typing import cast

from examples.targets.fraud_sparkov.constants import AMT_HIGH, NIGHT_HOURS
from examples.targets.fraud_sparkov.record import SparkovTxn


def is_fraud(sample: object) -> bool:
    rec = cast(SparkovTxn, sample)
    # Night-hour transactions are fraud regardless of amount (the dominant
    # signal in the real data). OR: high-amount transactions in a risky
    # category. cat_risk already encodes "category in risky set".
    return rec.hour in NIGHT_HOURS or (rec.cat_risk == 1 and rec.amt > AMT_HIGH)
