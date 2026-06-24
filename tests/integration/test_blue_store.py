"""Blue store persistence on real Postgres: patches, versions, held-out runs.

Saves a patch and its downstream rows and reads them back, so the /blue/:patchId
view and the SR 11-7 report (later slices) read real rows. No mocks of the
database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from sqlalchemy import delete, select

from modules.blue import BlueStore
from shared.persistence import get_sessionmaker
from shared.persistence.models import AgentConfig as AgentConfigRow
from shared.persistence.models import BluePatch as BluePatchRow
from shared.persistence.models import HoldoutRun as HoldoutRunRow
from shared.persistence.models import ModelVersion as ModelVersionRow
from shared.types import AuditStep, AuditTrace, BluePatch, PatchId, TargetType


@pytest_asyncio.fixture(autouse=True)
async def _clean_blue(migrated_database: str) -> AsyncIterator[None]:
    """Clear the blue tables before each test (children first for the FKs).

    The test database persists across runs and model_versions/agent_configs carry
    unique constraints, so a re-run would otherwise collide on a fixed version.
    """
    async with get_sessionmaker()() as session:
        await session.execute(delete(HoldoutRunRow))
        await session.execute(delete(ModelVersionRow))
        await session.execute(delete(AgentConfigRow))
        await session.execute(delete(BluePatchRow))
        await session.commit()
    yield


def _patch(target_type: TargetType, kind: str) -> BluePatch:
    return BluePatch(
        patch_id=PatchId.new(),
        target_type=target_type,
        kind=kind,
        detail={"provenance": ["a1", "a2"], "note": "fixture"},
        audit=AuditTrace(summary="fixture patch", steps=(AuditStep(label="x", detail={}),)),
    )


async def test_fraud_patch_round_trips_with_version_and_holdout(
    migrated_database: str,
) -> None:
    patch = _patch(TargetType.FRAUD, "retrain")
    async with get_sessionmaker()() as session:
        store = BlueStore(session=session)
        await store.save_patch(patch)
        await store.save_model_version(
            patch, version=2, kind="retrain", artifact_ref="artifacts/fraud-v2.lgb",
            metrics={"auc": 0.87},
        )
        await store.save_holdout_run(
            patch,
            {
                "holdout_size": 10,
                "detection_before": 0.0,
                "detection_after": 0.8,
                "recovered": True,
            },
        )
        await session.commit()

    async with get_sessionmaker()() as session:
        store = BlueStore(session=session)
        patches = await store.patches_for(TargetType.FRAUD)
        assert any(p.id == patch.patch_id.value for p in patches)

        version = (
            await session.execute(
                select(ModelVersionRow).where(ModelVersionRow.patch_id == patch.patch_id.value)
            )
        ).scalar_one()
        assert version.version == 2
        assert version.metrics["auc"] == 0.87

        holdout = (
            await session.execute(
                select(HoldoutRunRow).where(HoldoutRunRow.patch_id == patch.patch_id.value)
            )
        ).scalar_one()
        assert holdout.recovered is True
        assert holdout.detection_after == 0.8


async def test_agent_config_versions_increment(migrated_database: str) -> None:
    patch = _patch(TargetType.CODE_AGENT, "prompt_config")
    async with get_sessionmaker()() as session:
        store = BlueStore(session=session)
        await store.save_patch(patch)
        first = await store.next_agent_config_version()
        await store.save_agent_config(
            patch, version=first, system_prompt="Be strict.", config={"temperature": 0.0}
        )
        await session.commit()

    async with get_sessionmaker()() as session:
        store = BlueStore(session=session)
        nxt = await store.next_agent_config_version()
        assert nxt == first + 1
        row = (
            await session.execute(
                select(AgentConfigRow).where(AgentConfigRow.version == first)
            )
        ).scalar_one()
        assert row.system_prompt == "Be strict."
