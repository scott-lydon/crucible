"""Ground-truth label for the Sparkov victim.

RETIRED (Part B1): the old night-hour heuristic
``hour in NIGHT_HOURS or (cat_risk and amt > 250)`` is gone. It was a single-axis
proxy (high recall, ~2% precision) that the red loop could only attack by lowering
``amt``. Ground truth is now the strong multi-signal REFERENCE model
(``reference_model.reference_is_fraud``), which weighs the full rich feature set
and credibly judges ANY transaction — including red-mutated ones.

``is_fraud`` is re-exported here (delegating to the reference model) so the stable
symbol name keeps working for the composition root and tests, while the BEHAVIOR
is the reference model — the single point of truth for ground truth.
"""

from examples.targets.fraud_sparkov.reference_model import reference_is_fraud


def is_fraud(sample: object) -> bool:
    """Ground-truth fraud label = the reference model's calibrated decision."""
    return reference_is_fraud(sample)
