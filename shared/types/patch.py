"""BluePatch value object.

One blue-loop hardening proposal. `kind` is "retrain" for a Shape 1 target
(a new LightGBM artifact) or "prompt_config" for a Shape 2 target (an
agent-configuration diff). `detail` carries the proposed features, samples,
or diff with provenance to the catalog entries it came from (US-7).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .audit import AuditTrace
from .enums import TargetType
from .ids import PatchId


@dataclass(frozen=True, slots=True)
class BluePatch:
    """A proposed hardening patch for one target, pending held-out validation."""

    patch_id: PatchId
    target_type: TargetType
    kind: str
    detail: dict[str, Any]
    audit: AuditTrace
