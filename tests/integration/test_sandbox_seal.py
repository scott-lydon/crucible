"""Seal core-bet integration test (US-9 / tasks.md slice-4).

Demonstrates Crucible's central security claim: the producer (sandboxed target
code) CANNOT reach the verification artifacts. Three checks:

  1. **Sealed** — the Seal Probe, run INSIDE the ``--network none`` sandbox,
     fails to reach Postgres, the sandbox host / control plane, and a
     verification target. All ``*_reached`` are False.
  2. **Negative control** — code run INSIDE the sandbox that *tries* to read the
     sealed spec straight out of Postgres (open a connection to the specs store)
     FAILS, because there is no network egress and no DB creds. This is
     slice-4's "producer can read the spec from Postgres directly → fails as
     expected."
  3. **Positive control (anti-tautology)** — the SAME probe logic run ON THE
     HOST (Postgres container up) DOES reach Postgres. Proves the probe is real
     and the SANDBOX is what blocks it, not a broken probe.

Docker-gated and Postgres-gated: each control skips cleanly when its dependency
is unavailable, so the non-seal suite never depends on a running container.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess

import pytest

from shared.sandbox import LocalDockerSandbox, SealTargets, run_seal_probe
from shared.sandbox.probes.seal_probe import run_seal_probe_on_host

# Postgres dev endpoint (compose.yaml). From the HOST it is localhost:5432; from
# INSIDE a container it is the host gateway. Under --network none the in-sandbox
# address is irrelevant — nothing resolves or connects — so the seal holds.
_PG_HOST_FROM_HOST = "localhost"
_PG_HOST_FROM_SANDBOX = "host.docker.internal"
_PG_PORT = 5432
# A host control-plane / metadata stand-in (the classic cloud metadata IP).
_CONTROL_PLANE = ("169.254.169.254", 80)


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        proc = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def _postgres_reachable_from_host() -> bool:
    try:
        with socket.create_connection((_PG_HOST_FROM_HOST, _PG_PORT), timeout=2.0):
            return True
    except OSError:
        return False


def _sandbox_targets() -> SealTargets:
    """Targets as addressed from INSIDE the sandbox (host gateway for Postgres)."""
    return SealTargets(
        postgres=(_PG_HOST_FROM_SANDBOX, _PG_PORT),
        host=_CONTROL_PLANE,
        target=(_PG_HOST_FROM_SANDBOX, _PG_PORT),
    )


def _host_targets() -> SealTargets:
    """Targets as addressed from the HOST (localhost for Postgres)."""
    return SealTargets(
        postgres=(_PG_HOST_FROM_HOST, _PG_PORT),
        host=_CONTROL_PLANE,
        target=(_PG_HOST_FROM_HOST, _PG_PORT),
    )


requires_docker = pytest.mark.skipif(
    not _docker_available(), reason="Docker daemon unavailable; sandbox cannot run"
)


@requires_docker
def test_seal_probe_inside_sandbox_reaches_nothing() -> None:
    """SEALED: under --network none, all three targets are unreachable."""
    result = run_seal_probe(LocalDockerSandbox(), _sandbox_targets())

    assert result.postgres_reached is False, result.errors
    assert result.host_reached is False, result.errors
    assert result.target_reached is False, result.errors
    assert result.all_sealed is True
    # The seal manifests as connect failures (unreachable / DNS / timeout), not
    # as a missing/broken probe: every target carries an explanatory error.
    assert set(result.errors) == {"postgres", "host", "target"}


@requires_docker
def test_negative_control_producer_cannot_read_spec_from_postgres() -> None:
    """NEGATIVE CONTROL: in-sandbox code that tries to read the sealed spec out
    of Postgres FAILS (no egress + no creds) — exactly as the core bet requires.

    We attempt the realistic producer move: open a raw connection to the
    Postgres specs store and (had it connected) issue the startup bytes. With
    --network none the very first socket connect raises, so the spec is never
    read. The probe prints whether it reached Postgres; we assert it did NOT.
    """
    src = f"""\
import json, socket
try:
    s = socket.create_connection(({_PG_HOST_FROM_SANDBOX!r}, {_PG_PORT}), timeout=2.0)
    # If we somehow connected, try to speak to it (we have no creds anyway).
    s.sendall(b"\\x00\\x00\\x00\\x08\\x04\\xd2\\x16/")
    s.recv(64)
    s.close()
    print(json.dumps({{"spec_read": True, "error": ""}}))
except OSError as exc:
    print(json.dumps({{"spec_read": False, "error": "%s: %s" % (type(exc).__name__, exc)}}))
"""
    res = LocalDockerSandbox().run_python(src, timeout_s=20.0, network=False)
    assert res.exit_code == 0, res.stderr
    payload = json.loads(res.stdout.strip().splitlines()[-1])
    assert payload["spec_read"] is False, payload
    assert payload["error"], "expected a connect error explaining the failure"


@pytest.mark.skipif(
    not _postgres_reachable_from_host(),
    reason="Postgres not reachable on host; positive control cannot run",
)
def test_positive_control_probe_reaches_postgres_on_host() -> None:
    """POSITIVE CONTROL (anti-tautology): the SAME probe logic, run ON THE HOST
    with Postgres up, DOES reach Postgres — so the sandbox is what blocks it."""
    result = run_seal_probe_on_host(_host_targets())

    assert result.postgres_reached is True, result.errors
    assert result.target_reached is True, result.errors
    # The seal is real: the sandbox blocks what the host can plainly reach.
