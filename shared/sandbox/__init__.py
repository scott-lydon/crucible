"""Producer sandbox: Docker-backed sealed execution (Modal as the hosted target)."""

from __future__ import annotations

from .check_runner import CheckOutcome, CheckResult, run_python_checks
from .docker_sandbox import DockerSandbox
from .errors import SandboxLaunchError
from .models import SandboxResult

__all__ = [
    "CheckOutcome",
    "CheckResult",
    "DockerSandbox",
    "SandboxLaunchError",
    "SandboxResult",
    "run_python_checks",
]
