"""Typed sandbox errors.

Loud and specific per coding-practices.md section 6: the message names the
stage that failed (docker missing, launch, or timeout) and the likely fix.
"""

from __future__ import annotations

from shared.types import CrucibleError


class SandboxLaunchError(CrucibleError):
    """The producer sandbox could not be launched or did not return in time.

    Names whether docker was missing, the launch failed, or the job timed out,
    so the operator knows whether to install docker, start the daemon, or raise
    the timeout.
    """
