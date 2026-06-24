"""Blue module (Pillar 3): patch proposer, retrainer, held-out validator
(slice 14).
"""

from __future__ import annotations

from .errors import BlueError, HoldoutContamination, RetrainFailed
from .holdout_validator import HoldoutValidator
from .proposer import BlueProposer
from .retrainer import CodeConfigResult, Retrainer, RetrainResult, fraud_scorer
from .store import BlueStore

__all__ = [
    "BlueError",
    "BlueProposer",
    "BlueStore",
    "CodeConfigResult",
    "HoldoutContamination",
    "HoldoutValidator",
    "RetrainFailed",
    "RetrainResult",
    "Retrainer",
    "fraud_scorer",
]
