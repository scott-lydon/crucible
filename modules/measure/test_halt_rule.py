import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from modules.measure.halt_rule import (
    DEFAULT_HALT_RECALL_THRESHOLD,
    evaluate_halt,
    halt_recall_threshold,
    halt_status,
)
from shared.persistence import create_all, make_engine, make_session_factory, repo
from shared.persistence.models import RunRow, WhiteBoxMetricsRow


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)


async def _wb(sf: async_sessionmaker[AsyncSession], recall: float | None) -> None:
    rid = str(uuid.uuid4())
    async with sf() as s:
        s.add(RunRow(id=rid, seed="s", status="complete", n_rounds=2, batch_size=2,
                     threshold=0.5, params_json={}))
        await s.commit()
        await repo.upsert_white_box_metrics(s, WhiteBoxMetricsRow(
            run_id=rid, white_box_run_id="wb", black_box_catch_rate=0.9,
            white_box_catch_rate=recall, white_box_gap=None))


def test_threshold_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CRUCIBLE_HALT_RECALL_THRESHOLD", raising=False)
    assert halt_recall_threshold() == DEFAULT_HALT_RECALL_THRESHOLD


def test_threshold_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CRUCIBLE_HALT_RECALL_THRESHOLD", "0.5")
    assert halt_recall_threshold() == 0.5


async def test_no_metrics_not_halted(sf: async_sessionmaker[AsyncSession]) -> None:
    async with sf() as s:
        status = await evaluate_halt(s)
    assert status.halted is False
    assert status.recall is None  # undefined, NOT a fabricated 0.0


async def test_recall_below_threshold_halts(
    sf: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CRUCIBLE_HALT_RECALL_THRESHOLD", raising=False)
    await _wb(sf, recall=0.4)
    async with sf() as s:
        status = await evaluate_halt(s)
    assert status.halted is True
    assert status.recall == 0.4
    assert status.threshold == 0.7


async def test_recall_above_threshold_not_halted(
    sf: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CRUCIBLE_HALT_RECALL_THRESHOLD", raising=False)
    await _wb(sf, recall=0.85)
    async with sf() as s:
        status = await evaluate_halt(s)
    assert status.halted is False


async def test_halt_state_persists(
    sf: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CRUCIBLE_HALT_RECALL_THRESHOLD", raising=False)
    await _wb(sf, recall=0.3)
    async with sf() as s:
        await evaluate_halt(s)
    # a fresh status read sees the persisted halt (survives without re-eval)
    async with sf() as s:
        status = await halt_status(s)
    assert status.halted is True and status.recall == 0.3
