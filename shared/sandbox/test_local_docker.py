"""Real integration tests for the local Docker sandbox.

These tests run actual containers (no mocks). They require a working Docker
daemon. The first test may pull `python:3.12-slim`, which can take a while.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

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


# All tests carry the `docker` marker. Tests that exercise a *real* container
# are additionally gated behind `requires_docker`; the fail-loud test below
# simulates Docker's absence and so must run even where Docker is present.
pytestmark = pytest.mark.docker

requires_docker = pytest.mark.skipif(
    not _docker_available(), reason="Docker daemon not available"
)


@pytest.fixture(scope="module")
def sandbox() -> LocalDockerSandbox:
    return LocalDockerSandbox()


@requires_docker
def test_runs_code(sandbox: LocalDockerSandbox) -> None:
    # First test in the module: allow time for the image pull on a cold host.
    result = sandbox.run_python("print(2 + 2)", timeout_s=120.0)
    assert result.stdout.strip() == "4"
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.job_id  # uuid string present


@requires_docker
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
    assert result.timed_out is False
    # Prove the failure is network unreachability *specifically*, not some other
    # error that would let this test pass vacuously. The real run raises
    # `OSError: [Errno 101] Network is unreachable`.
    stderr_lower = result.stderr.lower()
    assert "unreachable" in stderr_lower or "errno 101" in stderr_lower, (
        f"expected a network-unreachable signal in stderr, got: {result.stderr!r}"
    )


@requires_docker
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


@requires_docker
def test_timeout(sandbox: LocalDockerSandbox) -> None:
    result = sandbox.run_python("while True:\n    pass\n", timeout_s=3.0)
    assert result.timed_out is True
    assert result.exit_code == 124
    # The whole point of the timeout path: untrusted code must not keep running.
    # Prove the container was reaped — no leaked `crucible-sbx-` container left.
    docker = shutil.which("docker")
    assert docker is not None
    leaked = ""
    for _ in range(25):  # up to ~5s for `docker kill`/`--rm` to settle
        ps = subprocess.run(
            [
                docker,
                "ps",
                "-a",
                "--filter",
                "name=crucible-sbx-",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
            timeout=30.0,
        )
        leaked = ps.stdout.strip()
        if not leaked:
            break
        time.sleep(0.2)
    assert leaked == "", f"timed-out container was not reaped; leaked: {leaked!r}"


def test_docker_unavailable_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate Docker being absent by making CLI lookup fail, then assert the
    # fail-loud contract: run_python raises the typed DockerUnavailableError.
    # This must run even where Docker exists (it simulates absence), so it is
    # NOT gated behind the docker-available skip. The module looks up the CLI via
    # `shutil.which`; making it return None is exactly "Docker not on PATH".
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    sandbox = LocalDockerSandbox()
    with pytest.raises(DockerUnavailableError):
        sandbox.run_python("print('should never run')", timeout_s=5.0)
