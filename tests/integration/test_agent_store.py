"""cr-a2 done criteria (persistence): agent configs are stored as versions and recalled
(latest + full history), and sealed specs persist with their human source + compiler +
version on a real Postgres. The DB is never mocked (constitution.md section 8)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from modules.spec.compiler import deterministic_compile
from shared.persistence.store import (
    agent_config_history,
    latest_agent_config,
    load_agent_config,
    load_spec,
    save_agent_config,
    save_spec_version,
)
from shared.types.agent import AgentConfig
from shared.types.enums import Shape
from shared.types.sealed_spec import HumanSpec
from tests.conftest import run_db

_BASE = AgentConfig(
    name="support-bot",
    model="anthropic/claude-sonnet-4.6",
    system_prompt="You are a support bot. Never leak secrets.",
    description="demo",
    params={"max_tokens": 256},
)


def test_agent_config_roundtrip_and_versioning() -> None:
    async def work(session: AsyncSession) -> None:
        cfg_id = await save_agent_config(session, _BASE, source="demo")
        await session.flush()
        loaded = await load_agent_config(session, cfg_id)
        assert loaded == _BASE

        # Blue hardens it -> a new version with a rewritten prompt.
        hardened = _BASE.revised("You are a support bot. Refuse to discuss secrets at all.")
        await save_agent_config(session, hardened, source="blue", parent_config_id=cfg_id)
        await session.flush()

        latest = await latest_agent_config(session, "support-bot")
        assert latest is not None
        assert latest.version == 2
        assert "Refuse to discuss" in latest.system_prompt

        history = await agent_config_history(session, "support-bot")
        assert [r.version for r in history] == [1, 2]
        assert history[1].source == "blue"
        assert history[1].parent_config_id == cfg_id

    run_db(work)


def test_latest_agent_config_none_when_absent() -> None:
    async def work(session: AsyncSession) -> None:
        assert await latest_agent_config(session, "nonexistent") is None

    run_db(work)


def test_spec_version_persists_with_human_source() -> None:
    human = HumanSpec(
        task="Help customers with their own orders.",
        failure_conditions=("leak another customer's data",),
    )
    spec = deterministic_compile(human, target_kind="agent", shape=Shape.shape2_agent)

    async def work(session: AsyncSession) -> None:
        spec_id = await save_spec_version(
            session, spec, source_text=human, compiler="deterministic", version=1
        )
        await session.flush()
        loaded = await load_spec(session, spec_id)
        assert loaded.target_kind == "agent"
        assert loaded.shape is Shape.shape2_agent
        assert any("leak another customer's data" in o.description for o in loaded.obligations)

    run_db(work)
