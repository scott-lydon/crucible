"""Slice 5 done-criterion: the producer cannot read held_out_tests rows.

A held-out test row is persisted server-side. From inside the sealed sandbox
(no network), a producer cannot reach Postgres at all, so it cannot read that
row, credentials or not. This is the read-side counterpart to the spec seal.
"""

from __future__ import annotations

import json
import shutil
import uuid

import pytest
from httpx import AsyncClient

from shared.persistence import get_sessionmaker
from shared.persistence.models import HeldOutTest
from shared.sandbox import DockerSandbox
from shared.sandbox.probes import SEAL_PROBE_PATH

_DUMMY_RUN = {
    "target_type": "dummy",
    "artifact_ref": "dummy-v0",
    "spec": {"title": "t", "obligations": [{"id": "o1", "description": "d"}]},
    "budget": {"max_attempts": 1, "max_dollars": 1.0},
}

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None,
    reason="docker required to run the sealed sandbox",
)


async def test_producer_cannot_read_held_out_tests(client: AsyncClient) -> None:
    # A real run, so the held_out_tests foreign key resolves.
    resp = await client.post("/runs", json=_DUMMY_RUN)
    run_id = resp.json()["run_id"]

    async with get_sessionmaker()() as session:
        session.add(
            HeldOutTest(
                id=uuid.uuid4().hex,
                run_id=run_id,
                spec_id="spec-x",
                test_code="assert True",
            )
        )
        await session.commit()

    # From inside the sealed sandbox the producer cannot reach Postgres, so the
    # held_out_tests row above is unreadable from the producer.
    source = SEAL_PROBE_PATH.read_text(encoding="utf-8")
    result = await DockerSandbox().run_python(source, args=["host.docker.internal", "5434"])
    report = json.loads(result.stdout)
    assert report["postgres_reachable"] is False
