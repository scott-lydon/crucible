"""The base class for typed, diagnosable Crucible errors.

Loud and specific (coding-practices.md section 6): a subclass names the operation
that failed and the inputs in play, so a failure is diagnosable from the message
alone rather than surfacing to the operator as a bare "Internal server error".
"""

from __future__ import annotations


class CrucibleError(Exception):
    """Base for every typed error the platform raises at an interface boundary."""
