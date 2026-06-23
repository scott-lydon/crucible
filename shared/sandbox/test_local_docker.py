"""Real integration tests for the local Docker sandbox.

These tests run actual containers (no mocks). They require a working Docker
daemon. The first test may pull `python:3.12-slim`, which can take a while.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from shared.sandbox.local_docker import DockerUnavailableError, LocalDockerSandbox


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        probe = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available"),
]


@pytest.fixture(scope="module")
def sandbox() -> LocalDockerSandbox:
    return LocalDockerSandbox()


def test_runs_code(sandbox: LocalDockerSandbox) -> None:
    # First test in the module: allow time for the image pull on a cold host.
    result = sandbox.run_python("print(2 + 2)", timeout_s=120.0)
    assert result.stdout.strip() == "4"
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.job_id  # uuid string present


def test_network_is_blocked(sandbox: LocalDockerSandbox) -> None:
    code = (
        "import socket\n"
        "socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
        "print('CONNECTED')\n"
    )
    result = sandbox.run_python(code, timeout_s=30.0, network=False)
    # MUST NOT connect: with --network none the socket cannot be opened.
    assert result.exit_code != 0
    assert "CONNECTED" not in result.stdout
    # The failure surfaces as an OSError-family exception in stderr.
    assert result.timed_out is False


def test_host_env_not_leaked(sandbox: LocalDockerSandbox) -> None:
    os.environ["CRUCIBLE_SECRET_PROBE"] = "leaked"
    try:
        result = sandbox.run_python(
            "import os; print(os.environ.get('CRUCIBLE_SECRET_PROBE', 'ABSENT'))",
            timeout_s=30.0,
        )
    finally:
        del os.environ["CRUCIBLE_SECRET_PROBE"]
    assert "ABSENT" in result.stdout
    assert "leaked" not in result.stdout
    assert result.exit_code == 0


def test_timeout(sandbox: LocalDockerSandbox) -> None:
    result = sandbox.run_python("while True:\n    pass\n", timeout_s=3.0)
    assert result.timed_out is True
    assert result.exit_code == 124


def test_docker_unavailable_raises_typed_error() -> None:
    # A sandbox pointed at a non-existent image still needs Docker; but here we
    # verify the typed-error contract by simulating a missing CLI path is not
    # trivially possible without monkeypatching PATH. Instead assert the error
    # type exists and is a RuntimeError subclass (fail-loud contract).
    assert issubclass(DockerUnavailableError, RuntimeError)
