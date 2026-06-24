"""Persistence for the blue loop: patches, model versions, held-out runs (US-7).

A thin store over one session, the same pattern as the red StrategyCatalog: the
caller owns the transaction (these add and flush, the route or test commits). It
records the proposal, the new target version, and the held-out validation so the
dashboard's `/blue/:patchId` view and the SR 11-7 report read real rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import AgentConfig as AgentConfigRow
from shared.persistence.models import BluePatch as BluePatchRow
from shared.persistence.models import HoldoutRun as HoldoutRunRow
from shared.persistence.models import ModelVersion as ModelVersionRow
from shared.types import BluePatch, TargetType


@dataclass(frozen=True, slots=True)
class BlueStore:
    """Reads and writes the blue-loop tables over one database session."""

    session: AsyncSession

    async def save_patch(self, patch: BluePatch) -> None:
        """Persist a proposed patch to blue_patches (provenance rides detail)."""
        self.session.add(
            BluePatchRow(
                id=patch.patch_id.value,
                target_type=patch.target_type.value,
                kind=patch.kind,
                detail=patch.detail,
                provenance=patch.detail.get("provenance", []),
                pillar="blue",
                dollars_spent=Decimal("0"),
                seed="",
                audit_trace=patch.audit.as_json(),
            )
        )
        await self.session.flush()

    async def save_holdout_run(
        self, patch: BluePatch, validation: dict[str, Any]
    ) -> None:
        """Persist a held-out validation result to holdout_runs."""
        self.session.add(
            HoldoutRunRow(
                id=uuid.uuid4().hex,
                patch_id=patch.patch_id.value,
                target_type=patch.target_type.value,
                holdout_size=int(validation.get("holdout_size", 0)),
                detection_before=float(validation.get("detection_before", 0.0)),
                detection_after=float(validation.get("detection_after", 0.0)),
                recovered=bool(validation.get("recovered", False)),
                detail=validation,
                seed="",
            )
        )
        await self.session.flush()

    async def save_model_version(
        self, patch: BluePatch, *, version: int, kind: str, artifact_ref: str,
        metrics: dict[str, Any],
    ) -> None:
        """Record a hardened target version under the one model_versions schema."""
        self.session.add(
            ModelVersionRow(
                id=uuid.uuid4().hex,
                target_type=patch.target_type.value,
                version=version,
                kind=kind,
                artifact_ref=artifact_ref,
                patch_id=patch.patch_id.value,
                metrics=metrics,
            )
        )
        await self.session.flush()

    async def next_agent_config_version(self) -> int:
        """One past the highest agent-config version, or 1 when none exist."""
        highest = (
            await self.session.execute(select(func.max(AgentConfigRow.version)))
        ).scalar_one_or_none()
        return (highest + 1) if highest is not None else 1

    async def save_agent_config(
        self, patch: BluePatch, *, version: int, system_prompt: str,
        config: dict[str, Any],
    ) -> None:
        """Persist a new code-agent prompt-and-config version."""
        self.session.add(
            AgentConfigRow(
                id=uuid.uuid4().hex,
                version=version,
                system_prompt=system_prompt,
                config=config,
                patch_id=patch.patch_id.value,
            )
        )
        await self.session.flush()

    async def patches_for(self, target_type: TargetType) -> list[BluePatchRow]:
        """Every recorded patch for a target type, newest first (dashboard read)."""
        rows = (
            await self.session.execute(
                select(BluePatchRow)
                .where(BluePatchRow.target_type == target_type.value)
                .order_by(BluePatchRow.created_at.desc())
            )
        ).scalars().all()
        return list(rows)
