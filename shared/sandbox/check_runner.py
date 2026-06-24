"""Run assert-based checks against produced source in the sealed sandbox.

Shared by the held-out and metamorphic oracles (and any later assert-running
oracle). It draws the distinction that keeps a verdict honest: an
AssertionError means the producer violated a check (FAIL), while any other
exception means the generated check itself is malformed and the result is
inconclusive (ERROR), so the oracle must not blame the producer for its own
broken check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared.sandbox.docker_sandbox import DockerSandbox

_PASS_MARKER = "__CRUCIBLE_CHECKS_PASS__"


class CheckOutcome(StrEnum):
    """The result of running checks against produced source."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The outcome plus the last diagnostic line for the audit trail."""

    outcome: CheckOutcome
    detail: str


async def run_python_checks(sandbox: DockerSandbox, source: str, checks: str) -> CheckResult:
    """Compose source + assert checks, run in the sandbox, classify the result.

    PASS when every assert held, FAIL when an assertion failed (the producer
    violated a check), ERROR when the script raised anything else (a malformed
    check, an import error, a syntax error in the produced source).
    """
    script = f"{source}\n\n# --- checks ---\n{checks}\n\nprint({_PASS_MARKER!r})\n"
    result = await sandbox.run_python(script)
    if result.exit_code == 0 and _PASS_MARKER in result.stdout:
        return CheckResult(CheckOutcome.PASS, "all checks passed")
    stderr = result.stderr.strip()
    tail = stderr.splitlines()[-1] if stderr else f"exit {result.exit_code}"
    if "AssertionError" in stderr:
        return CheckResult(CheckOutcome.FAIL, tail)
    return CheckResult(CheckOutcome.ERROR, tail)
