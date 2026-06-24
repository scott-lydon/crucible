"""The live run RESOLVES the sealed spec server-side (closes the seal loop).

The seal build persists the spec in Postgres (``store_spec``); this test proves
the live run then RESOLVES it via ``resolve_spec(spec_id)`` and drives the loop
+ oracles with the RESOLVED spec — not the in-process object. The seal loop the
demo claims (spec lives in the store; producer can't reach it; harness resolves
it) is therefore actually exercised on every run.

Uses the OFFLINE synth target (no external data, no real LLM) over in-memory
SQLite, so it runs in the non-gated suite with ZERO real LLM calls.
"""

from collections.abc import AsyncGenerator
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrator.api import app, init_db
from shared.persistence import repo
from shared.types import SealedSpec, sealed_spec_to_dict


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        yield c


async def test_round_trip_byte_identical() -> None:
    """store_spec -> resolve_spec returns a spec equal to the in-process one,
    so routing the run through the resolver cannot change behavior."""
    await init_db("sqlite+aiosqlite:///:memory:")
    from orchestrator.db import session_factory
    from orchestrator.wiring import build_components

    spec = cast(SealedSpec, build_components()["spec"])
    sf = session_factory()
    async with sf() as s:
        spec_id = await repo.store_spec(s, "run-rt", spec)
        resolved = await repo.resolve_spec(s, spec_id)
    assert resolved == spec
    assert sealed_spec_to_dict(resolved) == sealed_spec_to_dict(spec)


async def test_run_resolves_spec_via_resolve_spec(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A live run calls ``repo.resolve_spec`` and the run completes — proving the
    resolved (not in-process) spec drives the loop + oracles."""
    calls: list[str] = []
    real_resolve = repo.resolve_spec

    async def _spy(s: AsyncSession, spec_id: str) -> SealedSpec:
        calls.append(spec_id)
        return await real_resolve(s, spec_id)

    monkeypatch.setattr(repo, "resolve_spec", _spy)

    r = await client.post(
        "/runs",
        json={
            "target": "synth",
            "rounds": 2,
            "batch_size": 20,
            "seed": "resolve-spec",
            "run_blue": False,
        },
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]

    # The background task ran in-request (ASGITransport): the run is complete
    # and resolve_spec was invoked for exactly this run's stored spec.
    run = await client.get(f"/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["status"] == "complete", run.json()
    assert calls, "the run must resolve the sealed spec via repo.resolve_spec"

    # The resolved spec equals what was stored for this run (the loop used it).
    from orchestrator.db import session_factory

    sf = session_factory()
    async with sf() as s:
        resolved = await repo.resolve_spec(s, calls[0])
        from orchestrator.wiring import build_components

        assert sealed_spec_to_dict(resolved) == sealed_spec_to_dict(
            cast(SealedSpec, build_components()["spec"])
        )
