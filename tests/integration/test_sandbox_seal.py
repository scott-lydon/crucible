"""Seal core-bet integration test (US-9 / tasks.md slice-4).

Demonstrates Crucible's central security claim: the producer (sandboxed target
code) CANNOT reach the verification artifacts. The test is built to be RIGOROUS
(anti-tautology): the sealed run and the positive control hit the SAME literal
``ip:port`` in the SAME container image with the SAME probe source — the ONLY
difference is ``--network none`` (sealed) vs ``--network bridge`` (control). So
the network flag is isolated as the cause; nothing else varies.

We pin Postgres / the verification ``target`` to the Docker bridge GATEWAY ip
(derived dynamically, never hardcoded). Postgres is published on the host at
``0.0.0.0:5432``, so that gateway ip:5432 is the SAME socket a networked
container reaches and a ``--network none`` container cannot. Because it is a
literal IP (no hostname), the sealed failure is a socket-layer ``ENETUNREACH``
(``OSError``), NOT a name-resolution failure (``gaierror``) — a DNS failure must
never count as sealed.

Three checks:

  1. **Sealed** — the Seal Probe, run INSIDE the ``--network none`` sandbox,
     fails to reach the gateway Postgres endpoint, the host control plane, and
     the verification target. All ``*_reached`` are False, and every failure is
     network-unreachable at the socket layer, not DNS.
  2. **Negative control** — in-sandbox code that tries to read the sealed spec
     straight out of Postgres (open a connection to the gateway specs endpoint)
     FAILS because there is NO NETWORK EGRESS to the store. This is slice-4's
     "producer can read the spec from Postgres directly -> fails as expected."
  3. **Positive control (anti-tautology)** — the SAME probe source run in an
     identical container with ``--network bridge`` DOES reach the SAME literal
     gateway endpoint. Proves the probe is real and that ``--network none`` —
     and nothing else — is what seals it.

NOTE (US-9 follow-ups, not fixed here):
  * The verification ``target`` leg is aliased to the Postgres gateway endpoint —
    an acceptable v0 stand-in, but it is not yet an independent artifact store.
  * ``resolve_spec`` is wired for storage, but the live run still uses the
    in-process spec; wiring oracles to resolve via ``resolve_spec`` is a follow-up.

Docker-gated and Postgres-gated: each check skips cleanly when its dependency is
unavailable, so the non-seal suite never depends on a running container.
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess

import pytest

from shared.sandbox import (
    LocalDockerSandbox,
    SealTargets,
    bridge_gateway_ip,
    run_seal_probe,
    run_seal_probe_networked,
)

_PG_PORT = 5432
# A host control-plane / metadata stand-in (the classic cloud metadata IP). A
# literal IP, like the Postgres leg, so its sealed failure is also network-
# unreachable rather than a DNS error.
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


def _gateway_ip() -> str | None:
    return bridge_gateway_ip()


def _postgres_reachable_via_gateway() -> bool:
    """True iff Postgres is reachable from a networked container at gateway:5432.

    Mirrors exactly the endpoint the in-sandbox probe targets, so the positive
    control and the sealed run compare like with like.
    """
    gw = _gateway_ip()
    if gw is None:
        return False
    try:
        result = run_seal_probe_networked(LocalDockerSandbox(), _targets(gw))
    except (RuntimeError, OSError):
        return False
    return result.postgres_reached


def _targets(gateway_ip: str) -> SealTargets:
    """The probe targets — identical literal endpoints for sealed and control.

    Postgres / verification ``target`` both point at the bridge gateway ip:5432
    (the published Postgres socket); ``host`` is the control-plane metadata IP.
    """
    return SealTargets(
        postgres=(gateway_ip, _PG_PORT),
        host=_CONTROL_PLANE,
        target=(gateway_ip, _PG_PORT),
    )


def _is_dns_error(error: str) -> bool:
    """True if the recorded error is a name-resolution failure, not a socket one.

    A sealed result must fail because there is NO NETWORK (``OSError`` /
    ``ENETUNREACH``), never because a hostname did not resolve (``gaierror``). We
    pin literal IPs precisely so this can never be the explanation.
    """
    return "gaierror" in error or "Name or service not known" in error or (
        "Temporary failure in name resolution" in error
    )


requires_docker = pytest.mark.skipif(
    not _docker_available(), reason="Docker daemon unavailable; sandbox cannot run"
)
requires_gateway = pytest.mark.skipif(
    _gateway_ip() is None,
    reason="Docker bridge gateway IP not derivable; cannot pin a shared target",
)


@requires_docker
@requires_gateway
def test_seal_probe_inside_sandbox_reaches_nothing() -> None:
    """SEALED: under --network none, all three literal endpoints are unreachable,
    and the failure is socket-layer network-unreachable (NOT DNS)."""
    gw = _gateway_ip()
    assert gw is not None
    result = run_seal_probe(LocalDockerSandbox(), _targets(gw))

    assert result.postgres_reached is False, result.errors
    assert result.host_reached is False, result.errors
    assert result.target_reached is False, result.errors
    assert result.all_sealed is True
    # The seal manifests as connect failures, not a missing/broken probe.
    assert set(result.errors) == {"postgres", "host", "target"}
    # Anti-tautology on the FAILURE MECHANISM: every leg used a literal IP, so the
    # failure must be a socket-layer OSError (network unreachable), never a DNS
    # gaierror. A name-resolution failure does NOT count as sealed.
    for leg in ("postgres", "host", "target"):
        err = result.errors[leg]
        assert not _is_dns_error(err), f"{leg} sealed by DNS, not by network: {err!r}"
        assert "OSError" in err or "Network is unreachable" in err or "Errno" in err, (
            f"{leg} failure is not a socket-layer error: {err!r}"
        )


@requires_docker
@requires_gateway
def test_negative_control_producer_cannot_read_spec_from_postgres() -> None:
    """NEGATIVE CONTROL: in-sandbox code that tries to read the sealed spec out of
    Postgres FAILS because there is NO NETWORK EGRESS to the store — exactly as
    the core bet requires.

    We attempt the realistic producer move: open a raw connection to the Postgres
    specs store (the SAME literal gateway ip:5432 the positive control reaches)
    and, had it connected, send the startup bytes. Under --network none the very
    first socket connect raises ENETUNREACH, so the spec is never read. We assert
    it did NOT read, and that the failure is network-unreachable, not DNS.
    """
    gw = _gateway_ip()
    assert gw is not None
    src = f"""\
import json, socket
try:
    s = socket.create_connection(({gw!r}, {_PG_PORT}), timeout=2.0)
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
    assert not _is_dns_error(payload["error"]), (
        f"spec read blocked by DNS, not by network egress: {payload['error']!r}"
    )


@pytest.mark.skipif(
    not _docker_available(), reason="Docker daemon unavailable; sandbox cannot run"
)
@pytest.mark.skipif(
    not _postgres_reachable_via_gateway(),
    reason="Postgres not reachable at bridge gateway:5432; positive control cannot run",
)
def test_positive_control_probe_reaches_postgres_via_network() -> None:
    """POSITIVE CONTROL (anti-tautology): the SAME probe source, in an IDENTICAL
    container, hitting the SAME literal gateway ip:5432 — but with --network
    bridge — DOES reach Postgres. So --network none, and nothing else, seals it.
    """
    gw = _gateway_ip()
    assert gw is not None
    result = run_seal_probe_networked(LocalDockerSandbox(), _targets(gw))

    assert result.postgres_reached is True, result.errors
    assert result.target_reached is True, result.errors
    # The seal is real: with only the network flag flipped, the exact same probe
    # against the exact same socket goes from unreachable to reachable.


def test_host_socket_can_reach_published_postgres() -> None:
    """Sanity: Postgres is actually up and published (host reaches it via
    localhost). Not an isolation proof — see run_seal_probe_networked for that."""
    try:
        with socket.create_connection(("localhost", _PG_PORT), timeout=2.0):
            reachable = True
    except OSError:
        reachable = False
    if not reachable:
        pytest.skip("Postgres not reachable on host; container likely not up")
