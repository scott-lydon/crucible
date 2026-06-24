"""Slice 4 done-criterion: the producer sandbox is sealed (US-9).

Inside the sandbox, the producer cannot reach Postgres or the internet, so the
spec and the verification artifacts are unreadable from inside the producer.
A host positive-control proves the probe actually detects reachability, so the
in-sandbox "unreachable" result is real, not a probe that always says no.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from shared.sandbox import DockerSandbox
from shared.sandbox.probes import SEAL_PROBE_PATH

_HAS_DOCKER = shutil.which("docker") is not None


@pytest.mark.skipif(not _HAS_DOCKER, reason="docker required to run the sealed sandbox")
async def test_sandbox_denies_network_to_postgres_and_internet() -> None:
    source = SEAL_PROBE_PATH.read_text(encoding="utf-8")
    result = await DockerSandbox().run_python(source, args=["host.docker.internal", "5434"])
    assert result.exit_code == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["postgres_reachable"] is False
    assert report["internet_reachable"] is False


def test_probe_detects_reachability_on_host() -> None:
    # Positive control: the same probe, on the host with a network, reaches the
    # internet. This proves the in-sandbox False results above are the seal
    # working, not a probe hardcoded to fail.
    source = SEAL_PROBE_PATH.read_text(encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-", "localhost", "5434"],
        input=source,
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )
    report = json.loads(completed.stdout)
    assert report["internet_reachable"] is True
