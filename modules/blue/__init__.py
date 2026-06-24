"""The REAL blue loop (Option B) — Crucible's code-engineering defender pillar.

Closes the co-evolution arc HONESTLY: the red loop's successful evasions and the
RAW data surface feed a code-engineering maker (``BlueCodeEngineer``, Opus) that
must DISCOVER the missing signal and WRITE a feature-engineering transform. The
harness runs that untrusted transform in the Docker sandbox, retrains the victim
model on the base features PLUS the engineered column (via an injected victim
callback), validates detection RECOVERING on the held-out evasions, and ITERATES
with feedback. There is NO answer menu and NO guaranteed recovery — the maker is
allowed to fail.

This package is HARNESS code: it imports ONLY ``shared/`` and
``orchestrator/interfaces/``. The victim-specific raw surface + retraining
capability are INJECTED, keeping the harness target-agnostic.
"""

from modules.blue.code_engineer import (
    AttemptRecord,
    BlueCodeEngineer,
    EngineeredProposal,
)
from modules.blue.loop import BlueIteration, BlueResult, run_blue_round
from modules.blue.sandbox_transform import TransformError, run_transform_in_sandbox
from modules.blue.validator import HoldoutValidator, ValidationResult

__all__ = [
    "AttemptRecord",
    "BlueCodeEngineer",
    "BlueIteration",
    "BlueResult",
    "EngineeredProposal",
    "HoldoutValidator",
    "TransformError",
    "ValidationResult",
    "run_blue_round",
    "run_transform_in_sandbox",
]
