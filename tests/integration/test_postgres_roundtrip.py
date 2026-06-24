"""Gated dialect-parity check: round-trip a run row on REAL Postgres.

Proves the SQLAlchemy-generic schema is dialect-neutral — the same models that
the fast suite exercises on in-memory SQLite also create and round-trip on
Postgres. Skips cleanly (no failure) when no Postgres is reachable at the
default URL, so the suite never depends on a running container.
"""

import pytest

from orchestrator.db import DEFAULT_DATABASE_URL
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence.models import RunRow


async def _postgres_reachable(url: str) -> bool:
    engine = make_engine(url)
    try:
        async with engine.connect():
            return True
    except Exception:
        return False
    finally:
        await engine.dispose()


async def test_run_roundtrip_on_postgres() -> None:
    url = DEFAULT_DATABASE_URL
    if not await _postgres_reachable(url):
        pytest.skip("no Postgres reachable at default URL")

    engine = make_engine(url)
    await create_all(engine)
    sf = make_session_factory(engine)
    try:
        async with sf() as s:
            s.add(
                RunRow(
                    id="pg-roundtrip",
                    seed="42",
                    status="pending",
                    n_rounds=3,
                    batch_size=40,
                    threshold=0.5,
                    params_json={"target": "synth"},
                    pillar="orchestrator",
                )
            )
            await s.commit()
        async with sf() as s:
            got = await s.get(RunRow, "pg-roundtrip")
            assert got is not None
            assert got.n_rounds == 3
            assert got.params_json == {"target": "synth"}
            await s.delete(got)
            await s.commit()
    finally:
        await engine.dispose()
