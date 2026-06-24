"""SpecResolver round-trips a sealed spec through Postgres, id intact."""

from __future__ import annotations

import pytest

from shared.persistence import SpecNotFoundError, SpecResolver, get_sessionmaker
from shared.types import SealedSpec, SpecId


async def test_spec_resolver_round_trip(migrated_database: str) -> None:
    spec = SealedSpec.from_payload(
        {
            "title": "add two integers",
            "obligations": [{"id": "o1", "description": "return the sum"}],
            "invariants": [{"id": "i1", "description": "adding zero is a no-op"}],
        }
    )
    async with get_sessionmaker()() as session:
        resolver = SpecResolver(session)
        await resolver.save(spec)
        await session.commit()
        loaded = await resolver.get(spec.spec_id)

    assert loaded.spec_id == spec.spec_id
    assert loaded.title == "add two integers"
    assert loaded.obligations[0].id == "o1"
    assert loaded.invariants[0].id == "i1"


async def test_spec_resolver_missing_id_raises(migrated_database: str) -> None:
    async with get_sessionmaker()() as session:
        with pytest.raises(SpecNotFoundError, match="No sealed spec"):
            await SpecResolver(session).get(SpecId("does-not-exist"))
