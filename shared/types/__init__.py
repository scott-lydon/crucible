"""Shared domain types. Importing from ``shared.types`` is the supported surface;
submodules may be reorganized."""

from __future__ import annotations

from shared.types.core import (
    Attack,
    AttackBudget,
    AuditTrace,
    OracleVote,
    TargetSpec,
    Verdict,
)
from shared.types.enums import (
    OracleKind,
    Pillar,
    RunStatus,
    Shape,
    VerdictOutcome,
)
from shared.types.errors import CrucibleError
from shared.types.ids import (
    AttackId,
    LLMCallId,
    PatchId,
    RunId,
    SandboxJobId,
    VerdictId,
    new_id,
)
from shared.types.sealed_spec import Invariant, Obligation, SealedSpec

__all__ = [
    "Attack",
    "AttackBudget",
    "AttackId",
    "AuditTrace",
    "CrucibleError",
    "Invariant",
    "LLMCallId",
    "Obligation",
    "OracleKind",
    "OracleVote",
    "PatchId",
    "Pillar",
    "RunId",
    "RunStatus",
    "SandboxJobId",
    "SealedSpec",
    "Shape",
    "TargetSpec",
    "Verdict",
    "VerdictId",
    "VerdictOutcome",
    "new_id",
]
