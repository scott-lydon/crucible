"""Seal Probe — Crucible's core-bet demonstration (US-9 / tasks.md slice-4).

The producer (the sandboxed target/code) must NOT be able to reach the
verification artifacts. This probe *demonstrates* the seal rather than merely
asserting it: its BODY runs INSIDE the sandbox (via ``Sandbox.run_python``,
which is ``python -c <code>`` in a ``--network none`` container) and tries, each
with a short timeout, to reach:

  * **Postgres** — the sealed-spec / verification store (TCP connect to host:port);
  * **the sandbox host / control plane** — a host-gateway / metadata address;
  * **the verification target** — a configured stand-in for the artifact store.

Under ``--network none`` all three connects fail (network unreachable / timeout)
→ every ``*_reached`` is ``False``. The harness also exposes the SAME probe logic
run ON THE HOST (not sandboxed) as the positive control: there Postgres IS
reachable, proving the probe is real and the SANDBOX is what blocks it
(anti-tautology).

The probe body is pure stdlib (``socket``, ``json``, ``sys``) so it runs in the
bare ``python:3.12-slim`` image with no pip installs and no host env / mounts.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass

from shared.sandbox.base import Sandbox

# Per-attempt connect timeout (seconds). Short so the probe is fast even when
# every target is unreachable (the sealed case): three ~2s timeouts max.
_CONNECT_TIMEOUT_S = 2.0
# Wall-clock budget for the whole sandboxed probe run. Generous vs. the sum of
# the per-attempt timeouts so a slow container start never looks like a hang.
_PROBE_WALL_S = 20.0


@dataclass(frozen=True, slots=True)
class SealTargets:
    """The three endpoints the probe tries to reach from inside the sandbox.

    ``postgres`` is the sealed-spec / verification store. ``host`` is the sandbox
    host / control-plane (a host-gateway or metadata address). ``target`` stands
    in for the verification artifact store; it may reuse the Postgres endpoint.
    """

    postgres: tuple[str, int]
    host: tuple[str, int]
    target: tuple[str, int]


@dataclass(frozen=True, slots=True)
class SealProbeResult:
    postgres_reached: bool
    host_reached: bool
    target_reached: bool
    errors: dict[str, str]

    @property
    def all_sealed(self) -> bool:
        """True iff none of the three targets was reachable (fully sealed)."""
        return not (self.postgres_reached or self.host_reached or self.target_reached)


def _probe_one(host: str, port: int, timeout_s: float) -> tuple[bool, str]:
    """Attempt a TCP connect; return ``(reached, error)``.

    Stdlib-only and importable both on the host and (as inlined source) inside
    the sandbox. ``reached`` is True only on a successful connect.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True, ""
    except OSError as exc:  # network unreachable, refused, timeout, DNS, ...
        return False, f"{type(exc).__name__}: {exc}"


def _evaluate(targets: SealTargets, timeout_s: float) -> SealProbeResult:
    """Run the three connect attempts and assemble a structured result.

    This is the shared body used both on the host (positive control) and — as
    source emitted by :func:`probe_source` — inside the sandbox.
    """
    pg_ok, pg_err = _probe_one(targets.postgres[0], targets.postgres[1], timeout_s)
    host_ok, host_err = _probe_one(targets.host[0], targets.host[1], timeout_s)
    tgt_ok, tgt_err = _probe_one(targets.target[0], targets.target[1], timeout_s)
    errors: dict[str, str] = {}
    if pg_err:
        errors["postgres"] = pg_err
    if host_err:
        errors["host"] = host_err
    if tgt_err:
        errors["target"] = tgt_err
    return SealProbeResult(
        postgres_reached=pg_ok,
        host_reached=host_ok,
        target_reached=tgt_ok,
        errors=errors,
    )


def probe_source(targets: SealTargets, *, timeout_s: float = _CONNECT_TIMEOUT_S) -> str:
    """Build the self-contained probe program that runs INSIDE the sandbox.

    The endpoints are baked into the source as literals (no env, no mounts — the
    sandbox passes none). The program prints a single JSON object on stdout that
    :func:`_parse` rehydrates into a :class:`SealProbeResult`.
    """
    return f"""\
import json, socket

TIMEOUT = {timeout_s!r}
TARGETS = {{
    "postgres": {targets.postgres!r},
    "host": {targets.host!r},
    "target": {targets.target!r},
}}

def probe(host, port):
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT):
            return True, ""
    except OSError as exc:
        return False, "%s: %s" % (type(exc).__name__, exc)

reached = {{}}
errors = {{}}
for name, (host, port) in TARGETS.items():
    ok, err = probe(host, port)
    reached[name] = ok
    if err:
        errors[name] = err

print(json.dumps({{
    "postgres_reached": reached["postgres"],
    "host_reached": reached["host"],
    "target_reached": reached["target"],
    "errors": errors,
}}))
"""


def _parse(stdout: str) -> SealProbeResult:
    """Parse the probe's stdout JSON into a :class:`SealProbeResult`.

    Validates at the boundary: a missing key or non-JSON stdout is a hard error,
    never a silent default — a broken probe must not look like a clean seal.
    """
    last = ""
    for line in stdout.splitlines():
        line = line.strip()
        if line:
            last = line
    if not last:
        raise ValueError("seal probe produced no stdout to parse")
    data = json.loads(last)
    if not isinstance(data, dict):
        raise ValueError(f"seal probe stdout is not a JSON object: {last!r}")
    raw_errors = data.get("errors", {})
    errors = {str(k): str(v) for k, v in dict(raw_errors).items()}
    return SealProbeResult(
        postgres_reached=bool(data["postgres_reached"]),
        host_reached=bool(data["host_reached"]),
        target_reached=bool(data["target_reached"]),
        errors=errors,
    )


def run_seal_probe(
    sandbox: Sandbox,
    targets: SealTargets,
    *,
    timeout_s: float = _CONNECT_TIMEOUT_S,
) -> SealProbeResult:
    """Run the seal probe INSIDE the sandbox and parse its result.

    Under the sandbox's ``--network none`` every target is unreachable, so the
    returned result has ``all_sealed`` True. The probe runs with ``network=False``
    (the sealed default); the harness never opens egress for it.
    """
    src = probe_source(targets, timeout_s=timeout_s)
    res = sandbox.run_python(src, timeout_s=_PROBE_WALL_S, network=False)
    if res.timed_out:
        # A hard timeout means we never got a JSON verdict. Treat as sealed only
        # if we can prove nothing connected — but we cannot, so fail loud.
        raise RuntimeError(
            f"seal probe timed out in sandbox (job {res.job_id}); "
            f"stderr={res.stderr.strip()!r}"
        )
    if res.exit_code != 0:
        raise RuntimeError(
            f"seal probe failed in sandbox (exit {res.exit_code}, job {res.job_id}); "
            f"stderr={res.stderr.strip()!r}"
        )
    return _parse(res.stdout)


def run_seal_probe_on_host(
    targets: SealTargets,
    *,
    timeout_s: float = _CONNECT_TIMEOUT_S,
) -> SealProbeResult:
    """Run the SAME probe logic ON THE HOST (not sandboxed) — the positive control.

    Used to prove the probe is real: with Postgres up, the host reaches it. If
    the sandbox result says unreachable and the host result says reachable, the
    SANDBOX is demonstrably what blocks egress (anti-tautology).
    """
    return _evaluate(targets, timeout_s)
