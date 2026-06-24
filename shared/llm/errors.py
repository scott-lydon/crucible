"""Typed LLM errors.

Loud and specific per coding-practices.md section 6: the message names the
model, the failing stage (spawn, timeout, exit code, or parse), and the
captured stderr so a failed call is diagnosable without a debugger.
"""

from __future__ import annotations

from shared.types import CrucibleError


class LlmCallError(CrucibleError):
    """A `claude` CLI call failed: non-zero exit, timeout, or unparseable output.

    The message includes the model and the likely fix (for example, run
    `claude` once interactively to confirm the Max session is authenticated).
    """
