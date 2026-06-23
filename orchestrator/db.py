from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.persistence import make_engine, make_session_factory, create_all

_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(url: str = "sqlite+aiosqlite:///crucible.db") -> None:
    global _session_factory
    engine = make_engine(url)
    await create_all(engine)
    _session_factory = make_session_factory(engine)


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("init_db must be called before session_factory")
    return _session_factory
