from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    job_id: str
    timed_out: bool


class Sandbox(Protocol):
    def run_python(
        self, code: str, *, timeout_s: float = 10.0, network: bool = False
    ) -> SandboxResult: ...
