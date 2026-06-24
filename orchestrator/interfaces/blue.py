"""Blue-agent port.

The automated hardening loop. It reads the strategy catalog, proposes a
patch (new features or adversarial samples for the fraud target, a
prompt-and-configuration diff for the code agent), and validates the patch on
a held-out attack set defined up front (ARCHITECTURE.md section 3, Pillar 3).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from shared.types import Attack, BluePatch, TargetType


@runtime_checkable
class BlueAgent(Protocol):
    """The automated hardening engine over a single target type."""

    async def propose_patch(
        self,
        target_type: TargetType,
        catalog_slice: list[Attack],
    ) -> BluePatch:
        """Propose a hardening patch from a slice of undetected attacks."""
        ...

    async def validate_on_holdout(
        self,
        patch: BluePatch,
        holdout_attacks: list[Attack],
    ) -> dict[str, Any]:
        """Re-evaluate detection on a held-out attack set.

        The held-out set must never overlap the patch's training attacks; the
        orchestrator refuses to apply the patch otherwise (US-7). Returns the
        measured detection figures; the typed result shape is pinned in the
        blue-loop slice that builds the validator.
        """
        ...
