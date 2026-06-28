"""Typed orchestrator errors.

Loud and specific per coding-practices.md section 6: each names the operation that
failed and the inputs in play, so a failure is diagnosable from the message alone.
Ported from PR #3 (orchestrator/errors.py) onto main's container shape — the
``Registered: ...`` enumeration tells the operator exactly what IS wired so the fix
(register the adapter in wiring.py, or correct the run's target_kind) is obvious.
"""

from __future__ import annotations

from shared.types.errors import CrucibleError


class RunNotFoundError(CrucibleError):
    """A run id was looked up that does not exist in the runs table."""


class NoTargetRegisteredError(CrucibleError):
    """No target adapter is wired for the requested target kind.

    The message lists the registered target kinds so the fix (register the adapter in
    wiring.py, or correct the run's target_kind) is obvious.
    """


class NoOracleRegisteredError(CrucibleError):
    """No oracle is wired for the requested target kind.

    The message lists the target kinds that DO have oracles so the fix (register the
    oracle in wiring.py, or correct the target_kind) is obvious.
    """
