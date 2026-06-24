"""Persistence helpers for the Shape-2 agent path (cr-a2): versioned agent configs
and versioned sealed specs. The orchestrator and Blue pillar call these to store and
recall agent versions; the dashboard's spec-history and config-history screens read
them (cr-e3). Each takes the caller's session so it composes inside one unit of work."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import AgentConfigRow, SpecRow
from shared.types.agent import AgentConfig
from shared.types.ids import new_id
from shared.types.sealed_spec import HumanSpec, SealedSpec


async def save_agent_config(
    session: AsyncSession,
    config: AgentConfig,
    *,
    run_id: str | None = None,
    source: str = "byo",
    parent_config_id: str | None = None,
) -> str:
    """Persist one agent-config version; return its row id."""
    config_id = new_id("agentcfg")
    session.add(
        AgentConfigRow(
            id=config_id,
            run_id=run_id,
            name=config.name,
            version=config.version,
            model=config.model,
            system_prompt=config.system_prompt,
            description=config.description,
            params=dict(config.params),
            source=source,
            parent_config_id=parent_config_id,
        )
    )
    return config_id


def _row_to_config(row: AgentConfigRow) -> AgentConfig:
    return AgentConfig(
        name=row.name,
        model=row.model,
        system_prompt=row.system_prompt,
        description=row.description,
        params=dict(row.params),
        version=row.version,
    )


async def load_agent_config(session: AsyncSession, config_id: str) -> AgentConfig:
    row = (
        await session.execute(select(AgentConfigRow).where(AgentConfigRow.id == config_id))
    ).scalar_one()
    return _row_to_config(row)


async def latest_agent_config(session: AsyncSession, name: str) -> AgentConfig | None:
    """The highest-version config for an agent name, or None if none stored."""
    row = (
        await session.execute(
            select(AgentConfigRow)
            .where(AgentConfigRow.name == name)
            .order_by(AgentConfigRow.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return _row_to_config(row) if row is not None else None


async def agent_config_history(session: AsyncSession, name: str) -> list[AgentConfigRow]:
    """All versions of an agent, oldest first — the config-history surface."""
    return list(
        (
            await session.execute(
                select(AgentConfigRow)
                .where(AgentConfigRow.name == name)
                .order_by(AgentConfigRow.version.asc())
            )
        ).scalars()
    )


async def save_spec_version(
    session: AsyncSession,
    spec: SealedSpec,
    *,
    run_id: str | None = None,
    source_text: HumanSpec | None = None,
    compiler: str = "deterministic",
    version: int = 1,
    parent_spec_id: str | None = None,
) -> str:
    """Persist one sealed-spec version with its human source + how it was compiled."""
    session.add(
        SpecRow(
            id=spec.spec_id,
            run_id=run_id,
            target_kind=spec.target_kind,
            shape=str(spec.shape),
            holdout_generator_kind=spec.holdout_generator_kind,
            payload=spec.to_dict(),
            version=version,
            compiler=compiler,
            source_text=source_text.to_dict() if source_text is not None else None,
            parent_spec_id=parent_spec_id,
        )
    )
    return spec.spec_id


async def load_spec(session: AsyncSession, spec_id: str) -> SealedSpec:
    row = (
        await session.execute(select(SpecRow).where(SpecRow.id == spec_id))
    ).scalar_one()
    return SealedSpec.from_dict(row.payload)
