import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from shared.persistence import make_engine, make_session_factory, create_all
from shared.persistence.models import RunRow

@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    return make_session_factory(engine)

async def test_insert_and_read_run(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as s:
        run = RunRow(id="r1", seed="123", status="pending", n_rounds=5,
                     batch_size=200, threshold=0.5, params_json={}, pillar="orchestrator")
        s.add(run)
        await s.commit()
    async with session_factory() as s:
        got = await s.get(RunRow, "r1")
        assert got is not None and got.n_rounds == 5
