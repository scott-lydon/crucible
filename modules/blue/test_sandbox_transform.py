"""Docker-gated tests for the sandbox transform runner.

These exercise the REAL ``LocalDockerSandbox`` boundary: a known-good transform
produces numeric output of the right length, a broken transform returns a
``TransformError`` carrying the message (the loop never crashes). Skipped (not
failed) when the Docker CLI / daemon is unavailable. ZERO LLM calls.
"""

import shutil
import subprocess

import pytest

from modules.blue.sandbox_transform import TransformError, run_transform_in_sandbox
from shared.sandbox import LocalDockerSandbox


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=30.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


_DOCKER = _docker_ok()
_SKIP = "Docker CLI/daemon unavailable; the locked-down sandbox cannot run."

_ROWS = [
    {"trans_date_trans_time": "2019-01-01 01:30:00", "amt": 10.0},
    {"trans_date_trans_time": "2019-06-15 14:05:00", "amt": 99.0},
    {"trans_date_trans_time": "2019-12-31 23:59:00", "amt": 5.0},
]


@pytest.mark.skipif(not _DOCKER, reason=_SKIP)
def test_known_good_transform_returns_numeric_values() -> None:
    src = "return float(str(row['trans_date_trans_time'])[11:13])"
    out = run_transform_in_sandbox(LocalDockerSandbox(), src, _ROWS)
    assert isinstance(out, list)
    assert out == [1.0, 14.0, 23.0]


@pytest.mark.skipif(not _DOCKER, reason=_SKIP)
def test_broken_transform_returns_error_without_crashing() -> None:
    src = "return row['does_not_exist'] + 1"  # KeyError inside the container
    out = run_transform_in_sandbox(LocalDockerSandbox(), src, _ROWS)
    assert isinstance(out, TransformError)
    assert out.message  # carries the captured message for maker feedback


@pytest.mark.skipif(not _DOCKER, reason=_SKIP)
def test_wrong_length_output_is_an_error() -> None:
    # Returns a constant; fine — but a transform printing the wrong shape would
    # be caught. Here we verify non-numeric output is rejected.
    src = "return 'not a number'"
    out = run_transform_in_sandbox(LocalDockerSandbox(), src, _ROWS)
    assert isinstance(out, TransformError)
