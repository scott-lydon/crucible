"""TargetSpec value object.

Identifies which target adapter a run drives and the artifact it pins: a
model-file checksum for a Shape 1 target (the fraud LightGBM classifier),
an agent-configuration version for a Shape 2 target (the code agent).
"""

from __future__ import annotations

from dataclasses import dataclass

from .enums import TargetType
from .errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class TargetSpec:
    """Which target a run drives, and the exact artifact it is pinned to."""

    target_type: TargetType
    artifact_ref: str

    def __post_init__(self) -> None:
        if not self.artifact_ref:
            raise DomainValidationError(
                f"TargetSpec.artifact_ref must be non-empty for target_type "
                f"{self.target_type!r}; it pins the exact model checksum or "
                f"agent-config version under test so a run is reproducible."
            )
