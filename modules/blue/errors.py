"""Typed errors for the blue hardening loop (ARCHITECTURE.md section 3, Pillar 3).

These are module-local so the blue pillar owns its own failure vocabulary, the
same pattern as modules/targets/fraud/errors.py. They carry operator-readable
messages with no SQL or secrets, so surfacing the message at the API boundary
tells the operator exactly what to fix.
"""

from __future__ import annotations


class BlueError(Exception):
    """Base class for blue-loop failures."""


class HoldoutContamination(BlueError):  # noqa: N818 - name mandated verbatim by US-7
    """The held-out attack set overlaps the patch's training attacks (US-7).

    The orchestrator refuses to apply the patch: a held-out score that shares
    examples with the training set is not held-out, it is leakage, and would
    report a recovery the patch did not earn.
    """


class RetrainFailed(BlueError):  # noqa: N818 - name mandated verbatim by ARCHITECTURE.md
    """A retrain pass failed, naming the artifact version it was writing."""
