"""Public value-type surface for the shared layer.

Re-exported explicitly via ``__all__`` so that ``mypy --strict``
(no_implicit_reexport) treats these as the intended public names.
"""

from __future__ import annotations

from .attack import Attack
from .audit import AuditStep, AuditTrace
from .budget import AttackBudget
from .enums import Pillar, ProbeStatus, RunStatus, TargetType, VerdictDecision
from .errors import CrucibleError, DomainValidationError
from .ids import AttackId, LlmCallId, PatchId, RunId, SpecId, VerdictId
from .money import Money
from .patch import BluePatch
from .probe import ProbeResult
from .sealed_spec import Invariant, Obligation, SealedSpec
from .target_output import TargetOutput
from .target_spec import TargetSpec
from .verdict import OracleVote, Verdict

__all__ = [
    "Attack",
    "AttackBudget",
    "AttackId",
    "AuditStep",
    "AuditTrace",
    "BluePatch",
    "CrucibleError",
    "DomainValidationError",
    "Invariant",
    "LlmCallId",
    "Money",
    "Obligation",
    "OracleVote",
    "Pillar",
    "PatchId",
    "ProbeResult",
    "ProbeStatus",
    "RunId",
    "RunStatus",
    "SealedSpec",
    "SpecId",
    "TargetOutput",
    "TargetSpec",
    "TargetType",
    "Verdict",
    "VerdictDecision",
    "VerdictId",
]
