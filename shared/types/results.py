"""Result/value types that cross interface boundaries but are not themselves
persisted rows. Kept in shared/types so both the orchestrator interfaces and the
implementing modules can import them without importing each other."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from shared.types.core import AuditTrace


@dataclass(frozen=True, slots=True)
class ProducerResult:
    """What a Target returns for one submitted input. ``output`` is the producer's
    answer the oracles will check; ``audit`` carries the producer's own trace."""

    output: Mapping[str, Any]
    audit: AuditTrace
    dollars: float = 0.0
    sandbox_job_id: str | None = None


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """One subcomponent's self-test result (spec US-8)."""

    status: str                  # "green" | "amber" | "red" | "stub"
    detail: Mapping[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PatchResult:
    """What the Blue pillar returns from one hardening pass (spec US-7). The
    held-out before/after detection rates prove the patch generalized rather than
    memorized the attacks it was built from."""

    patch_id: str
    summary: str
    validated: bool
    holdout_detection_before: float
    holdout_detection_after: float
    audit: AuditTrace
    dollars: float = 0.0
    new_model_version: str | None = None
