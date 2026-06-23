"""Local Docker sandbox: the producer-isolation mechanism for Crucible v1.

Runs untrusted Python (from the code-agent target) inside a fresh, throwaway
`python:3.12-slim` container with strict isolation:

  * no network (``--network none``) unless explicitly requested,
  * no host environment / secrets (clean env; we never pass ``-e``/``--env-file``),
  * resource limits (``--memory``, ``--cpus``, ``--pids-limit``),
  * a non-root user (``--user 65534:65534`` / nobody),
  * a hard wall-clock timeout enforced by the parent process.

This adapter satisfies the :class:`shared.sandbox.base.Sandbox` Protocol so that a
different backend (e.g. Modal) can be swapped in later without touching callers.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid

from shared.sandbox.base import SandboxResult

_IMAGE = "python:3.12-slim"
_MEMORY_LIMIT = "256m"
_CPU_LIMIT = "1"
_PIDS_LIMIT = "128"
# nobody:nogroup — avoids running untrusted code as root inside the container.
_USER = "65534:65534"
# Grace period (seconds) we wait for `docker kill` to reap a timed-out container
# before giving up. The container is also `--rm`, so it self-removes once killed.
_KILL_TIMEOUT_S = 10.0


class DockerUnavailableError(RuntimeError):
    """Raised when the Docker CLI is missing or the daemon is unreachable.

    We fail loud here rather than silently degrading: a non-functional sandbox
    must never look like a clean run of untrusted code.
    """


class LocalDockerSandbox:
    """A :class:`~shared.sandbox.base.Sandbox` backed by ``docker run``."""

    def __init__(self, image: str = _IMAGE) -> None:
        self._image = image

    def _docker_path(self) -> str:
        path = shutil.which("docker")
        if path is None:
            raise DockerUnavailableError(
                "docker CLI not found on PATH; the local sandbox cannot run "
                "untrusted code without Docker. Install Docker and ensure the "
                "daemon is running."
            )
        return path

    def _ensure_daemon(self, docker: str) -> None:
        try:
            probe = subprocess.run(
                [docker, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
                timeout=30.0,
            )
        except FileNotFoundError as exc:  # pragma: no cover - covered by _docker_path
            raise DockerUnavailableError(f"docker CLI not invocable: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise DockerUnavailableError(
                "docker daemon did not respond to `docker info` within 30s; "
                "is the daemon running?"
            ) from exc
        if probe.returncode != 0:
            raise DockerUnavailableError(
                "docker daemon is not available (`docker info` failed): "
                f"{probe.stderr.strip() or probe.stdout.strip()}"
            )

    def run_python(
        self, code: str, *, timeout_s: float = 10.0, network: bool = False
    ) -> SandboxResult:
        docker = self._docker_path()
        self._ensure_daemon(docker)

        job_id = str(uuid.uuid4())
        container_name = f"crucible-sbx-{job_id}"

        argv: list[str] = [
            docker,
            "run",
            "--rm",
            "--name",
            container_name,
            "--network",
            "bridge" if network else "none",
            f"--memory={_MEMORY_LIMIT}",
            f"--cpus={_CPU_LIMIT}",
            f"--pids-limit={_PIDS_LIMIT}",
            "--user",
            _USER,
            # Drop all Linux capabilities; untrusted code needs none of them.
            "--cap-drop",
            "ALL",
            # Prevent the process from gaining privileges via setuid binaries.
            "--security-opt",
            "no-new-privileges",
            # NOTE: deliberately no `-e` / `--env-file`: `docker run` does not
            # inherit the parent process environment, so host secrets stay out.
            self._image,
            "python",
            "-c",
            code,
        ]

        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                # Clean env for the docker client itself; it still talks to the
                # daemon over the default socket but inherits no host secrets.
                env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
            )
        except subprocess.TimeoutExpired as exc:
            self._kill_container(docker, container_name)
            stdout = _coerce(exc.stdout)
            stderr = _coerce(exc.stderr)
            return SandboxResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=124,
                job_id=job_id,
                timed_out=True,
            )

        return SandboxResult(
            stdout=completed.stdout,
            stderr=completed.stderr,
            exit_code=completed.returncode,
            job_id=job_id,
            timed_out=False,
        )

    @staticmethod
    def _kill_container(docker: str, name: str) -> None:
        """Best-effort reap of a timed-out container; it is also ``--rm``."""
        try:
            subprocess.run(
                [docker, "kill", name],
                capture_output=True,
                text=True,
                timeout=_KILL_TIMEOUT_S,
            )
        except (subprocess.TimeoutExpired, OSError):
            # We did our best; `--rm` will clean up when the container dies.
            pass


def _coerce(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
