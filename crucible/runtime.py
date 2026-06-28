"""Runtime probes shared by ``crucible doctor`` and the eligibility gate.

Each probe answers one yes/no with a specific fix string, never a vague failure. None of
these spend a cent: they shell out to local tooling or read a file."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    detail: str
    fix: str = ""


def claude_cli_available() -> ProbeResult:
    """The local Claude CLI on PATH (real-LLM runs invoke it). Mock runs do not need it."""
    path = shutil.which("claude")
    if path is None:
        return ProbeResult(
            False, "claude CLI not found on PATH",
            "Install the Claude Code CLI and ensure `claude` is on PATH "
            "(mock runs do not need it; only real-LLM runs do).")
    return ProbeResult(True, f"claude CLI at {path}")


def docker_running() -> ProbeResult:
    """The Docker daemon, needed by the producer sandbox (docker run --network none).
    A fraud-only run does not need it."""
    if shutil.which("docker") is None:
        return ProbeResult(
            False, "docker not found on PATH",
            "Install Docker Desktop and start it: open -a Docker")
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return ProbeResult(False, f"docker info failed: {exc}", "Start Docker: open -a Docker")
    if proc.returncode != 0:
        return ProbeResult(
            False, f"docker daemon not responding: {proc.stderr.strip()[:120]}",
            "Start the Docker daemon: open -a Docker")
    return ProbeResult(True, f"docker daemon up (server {proc.stdout.strip()})")


def artifact_present(path: str | Path) -> ProbeResult:
    p = Path(path)
    if p.exists():
        return ProbeResult(True, f"{p} present ({p.stat().st_size} bytes)")
    return ProbeResult(
        False, f"{p} missing",
        f"Train it: python -m scripts... or fetch the artifact to {p}")


# Targets whose producer executes code in the Docker sandbox (need the daemon).
CODE_SHAPED_TARGETS = frozenset({"code_agent"})


def target_needs_docker(target_kind: str) -> bool:
    return target_kind in CODE_SHAPED_TARGETS
