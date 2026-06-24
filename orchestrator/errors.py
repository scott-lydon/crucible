"""Typed orchestrator errors.

Loud and specific per coding-practices.md section 6: each names the operation
that failed and the inputs in play, so a failure is diagnosable from the
message alone.
"""

from __future__ import annotations

from shared.types import CrucibleError


class RunNotFoundError(CrucibleError):
    """A run id was looked up that does not exist in the runs table."""


class NoTargetRegisteredError(CrucibleError):
    """No target adapter is wired for the requested target type.

    The message lists the registered target types so the fix (register the
    adapter in wiring.py, or correct the run's target_type) is obvious.
    """


class NoOracleRegisteredError(CrucibleError):
    """No oracle is wired under the requested name.

    The message lists the registered oracle names so the fix (register the
    oracle in wiring.py, or correct the name) is obvious.
    """
