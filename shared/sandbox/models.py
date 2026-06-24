"""Sandbox result value object."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SandboxResult:
    """The outcome of one sandboxed execution.

    `job_id` ties the run to its persisted `sandbox_jobs` row (written by the
    caller when the loop uses the sandbox).
    """

    stdout: str
    stderr: str
    exit_code: int
    job_id: str
