"""Local producer sandbox — the Modal substitute (deviation tracked in bead cr-dev).

A producer runs inside an ephemeral ``docker run --rm --network none`` container with
no host environment and a read-only code mount, so it cannot reach Postgres, the
internet, or any verification artifact (constitution.md section 3, spec US-9). The
seal is enforced by the kernel (no network interface), not by application code.

Risk spike cr-r3 proved ``--network none`` blocks egress to both the host Postgres
and the internet."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.ext.asyncio import AsyncSession

from shared.persistence.models import SandboxJobRow
from shared.types.ids import new_id


@dataclass(frozen=True, slots=True)
class SandboxResult:
    job_ref: str
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    network: str
    env_applied: Mapping[str, str] = field(default_factory=dict)


class LocalDockerSandbox:
    def __init__(
        self,
        image: str = "python:3.12-slim",
        *,
        network: str = "none",
        timeout: float = 30.0,
        memory: str = "512m",
        pids_limit: int = 256,
    ) -> None:
        self.image = image
        self.network = network
        self.timeout = timeout
        self.memory = memory
        self.pids_limit = pids_limit

    async def run(
        self,
        main_script: str,
        *,
        files: Mapping[str, str] | None = None,
        argv: list[str] | None = None,
    ) -> SandboxResult:
        job_ref = new_id("sbx")
        with TemporaryDirectory(prefix="crucible-sbx-") as workdir:
            (Path(workdir) / "main.py").write_text(main_script, encoding="utf-8")
            for name, content in (files or {}).items():
                (Path(workdir) / name).write_text(content, encoding="utf-8")
            cmd = [
                "docker", "run", "--rm",
                "--network", self.network,
                "--memory", self.memory,
                f"--pids-limit={self.pids_limit}",
                "--cpus", "1",
                "-v", f"{workdir}:/sandbox:ro",
                "-w", "/sandbox",
                self.image,
                "python", "main.py", *(argv or []),
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=self.timeout
                )
                timed_out = False
            except TimeoutError:
                proc.kill()
                await proc.wait()
                stdout_b, stderr_b = b"", b""
                timed_out = True
        return SandboxResult(
            job_ref=job_ref,
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=(proc.returncode if proc.returncode is not None else -1),
            timed_out=timed_out,
            network=self.network,
            env_applied={},
        )


async def record_sandbox_job(
    session: AsyncSession,
    result: SandboxResult,
    *,
    run_id: str | None = None,
    seed: str = "",
) -> str:
    job_id = new_id("sbxjob")
    session.add(
        SandboxJobRow(
            id=job_id,
            run_id=run_id,
            job_ref=result.job_ref,
            env_applied=dict(result.env_applied),
            network_rules=f"network={result.network} (egress denied)",
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            seed=seed,
        )
    )
    return job_id
