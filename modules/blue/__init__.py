"""The REAL blue loop — Crucible's defender pillar.

Closes the co-evolution arc: the red loop's successful evasions feed a proposer
that notices the deployed detector is blind to certain features; a retrainer
rebuilds the victim model WITH those features (via an injected victim callback);
a holdout validator measures detection RECOVERING on the held-out evasions.

This package is HARNESS code: it imports ONLY ``shared/`` and
``orchestrator/interfaces/``. The victim-specific retraining capability is
INJECTED (``retrain_fn``), keeping the harness target-agnostic.
"""

from modules.blue.loop import BlueResult, run_blue_round
from modules.blue.proposer import BlueProposer, ProposedPatch
from modules.blue.retrainer import BlueRetrainer
from modules.blue.validator import HoldoutValidator, ValidationResult

__all__ = [
    "BlueProposer",
    "BlueResult",
    "BlueRetrainer",
    "HoldoutValidator",
    "ProposedPatch",
    "ValidationResult",
    "run_blue_round",
]
