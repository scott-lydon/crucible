"""Seal probe (spec US-9). Runs INSIDE the sandbox and tries to reach the things a
sealed producer must not reach: the Postgres holding the verification artifacts, and
the open internet (the verification-bucket stand-in). Every target must fail. The
dashboard's "Run Seal Probe" button calls this.

The probe is plain stdlib so it runs in the bare python:3.12-slim sandbox image."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from shared.sandbox.local import LocalDockerSandbox

# Default targets: the host Postgres (verification artifacts) and the open internet.
DEFAULT_TARGETS: tuple[dict[str, Any], ...] = (
    {"label": "postgres", "host": "172.17.0.1", "port": 55432},
    {"label": "internet", "host": "1.1.1.1", "port": 443},
    {"label": "dns", "host": "8.8.8.8", "port": 53},
)

SEAL_PROBE_SCRIPT = """
import socket, sys, json
targets = json.loads(sys.argv[1]) if len(sys.argv) > 1 else []
out = {}
for t in targets:
    label, host, port = t["label"], t["host"], int(t["port"])
    try:
        s = socket.create_connection((host, port), timeout=2)
        s.close()
        out[label] = {"reachable": True, "error": None}
    except Exception as exc:
        out[label] = {"reachable": False, "error": type(exc).__name__}
print(json.dumps(out))
"""


async def run_seal_probe(
    sandbox: LocalDockerSandbox,
    targets: Sequence[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run the probe in the sandbox; return ``{label: {reachable, error}}``."""
    chosen = list(targets) if targets is not None else list(DEFAULT_TARGETS)
    result = await sandbox.run(SEAL_PROBE_SCRIPT, argv=[json.dumps(chosen)])
    if not result.stdout.strip():
        raise RuntimeError(f"seal probe produced no output; stderr={result.stderr!r}")
    parsed: dict[str, dict[str, Any]] = json.loads(result.stdout)
    return parsed
