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


@pytest.mark.skipif(not _DOCKER, reason=_SKIP)
def test_large_sample_does_not_blow_arg_limit() -> None:
    # REGRESSION (E2BIG): the rows used to be embedded as a JSON literal inside
    # the `python -c` code string, so at real data volume the command line blew
    # the OS argument-length limit ("argument list too long") and the transform
    # NEVER ran. Now the rows go in via stdin, so the command line stays small and
    # constant regardless of row count. Build a sample whose JSON is far larger
    # than ARG_MAX (~256 KiB on macOS/Linux) so the OLD argv path would E2BIG.
    big_rows = [
        {
            "trans_date_trans_time": "2019-01-01 01:30:00",
            "amt": 10.0,
            "pad": "x" * 200,  # ~250 B/row * 2000 rows ≈ 500 KiB JSON > ARG_MAX
        }
        for _ in range(2000)
    ]
    src = "return float(str(row['trans_date_trans_time'])[11:13])"
    out = run_transform_in_sandbox(LocalDockerSandbox(), src, big_rows)
    assert isinstance(out, list), out  # ran, not an E2BIG TransformError
    assert len(out) == len(big_rows)
    assert out[0] == 1.0 and out[-1] == 1.0
