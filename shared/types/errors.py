"""Typed domain errors for the shared value objects.

Every invalid construction raises a specific subclass so a bad input is
diagnosable from the message alone, per coding-practices.md section 6
("errors must be loud, typed, and self-explaining").
"""

from __future__ import annotations


class CrucibleError(Exception):
    """Base class for every Crucible-defined error.

    Catching this catches only errors Crucible raised on purpose, never an
    unrelated library failure.
    """


class DomainValidationError(CrucibleError):
    """A value object was constructed with a value that violates its contract.

    The message names the type, the rule, and the offending value so the fix
    is obvious without opening a debugger.
    """
