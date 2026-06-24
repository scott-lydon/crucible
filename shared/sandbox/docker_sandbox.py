"""Docker-backed producer sandbox.

Runs a Python snippet inside a container with no network and no inherited
environment, so produced code cannot reach Postgres, the host, or the
internet. This is the seal the core bet rests on (ARCHITECTURE.md section 11):
the verification artifacts are unreachable from inside the producer.

`docker run` is invoked with `--network none` (no egress) and without any `-e`
flags (the host environment, including secrets, is never passed in). The
hosted Modal path is a later swap behind the same call shape.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from shared.sandbox.errors import SandboxLaunchError
from shared.sandbox.models import SandboxResult

_DEFAULT_IMAGE = "python:3.12-slim"
_DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class DockerSandbox:
    """Executes Python in a sealed container (no network, no host env)."""

    image: str = _DEFAULT_IMAGE
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS

    async def run_python(self, code: str, args: list[str] | None = None) -> SandboxResult:
        """Run `code` as a Python script in a sealed container, returning its result.

        `code` is fed on stdin to `python -`; `args` become sys.argv[1:]. The
        container has no network (`--network none`) and no inherited env.
        """
        job_id = uuid.uuid4().hex
        cmd = ["docker", "run", "--rm", "--network", "none", "-i", self.image, "python", "-"]
        if args:
            cmd += args

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise SandboxLaunchError(
                "docker not found on PATH. Install Docker and start the daemon to "
                "run the producer sandbox, or switch the sandbox to the hosted "
                "Modal path."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=code.encode("utf-8")),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise SandboxLaunchError(
                f"sandbox job {job_id} timed out after {self.timeout_seconds:.0f}s. "
                f"Raise DockerSandbox.timeout_seconds or shorten the producer code."
            ) from exc

        return SandboxResult(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            job_id=job_id,
        )
