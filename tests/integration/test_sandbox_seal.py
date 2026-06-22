"""Slice-4 done criteria: the local sandbox runs code but seals all network egress,
so the producer cannot reach Postgres or the internet (spec US-9). The server-side
resolver, by contrast, reads the sealed spec — because it runs outside the sandbox."""

from __future__ import annotations

import asyncio
import shutil

import pytest
from fastapi.testclient import TestClient

from shared.persistence.resolver import resolve_spec
from shared.sandbox.local import LocalDockerSandbox
from shared.sandbox.probes.seal_probe import run_seal_probe
from tests.conftest import DUMMY_SPEC_YAML, run_db

_needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker not available"
)


@_needs_docker
def test_sandbox_runs_code() -> None:
    sandbox = LocalDockerSandbox()
    result = asyncio.run(sandbox.run("print('hello from sandbox')"))
    assert result.exit_code == 0, result.stderr
    assert "hello from sandbox" in result.stdout
    assert result.network == "none"


@_needs_docker
def test_seal_probe_blocks_postgres_and_internet() -> None:
    sandbox = LocalDockerSandbox()
    probe = asyncio.run(run_seal_probe(sandbox))
    # Every target — the verification Postgres and the open internet — must be blocked.
    assert probe["postgres"]["reachable"] is False, probe
    assert probe["internet"]["reachable"] is False, probe
    assert probe["dns"]["reachable"] is False, probe


def test_server_side_resolver_reads_spec(client: TestClient) -> None:
    # The orchestrator (outside the sandbox) CAN read the sealed spec via the resolver.
    resp = client.post(
        "/runs",
        json={
            "target_kind": "dummy",
            "shape": "shape1_ml",
            "spec_yaml": DUMMY_SPEC_YAML,
            "budget_rounds": 1,
            "budget_dollars": 1.0,
        },
    )
    run_id = resp.json()["runId"]
    spec = run_db(lambda session: resolve_spec(session, run_id))
    assert spec.spec_id == "dummy-demo-v1"
    assert any(o.obligation_id == "catch-fraud" for o in spec.obligations)
