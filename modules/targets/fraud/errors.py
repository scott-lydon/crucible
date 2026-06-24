"""Typed fraud-target errors."""

from __future__ import annotations

from shared.types import CrucibleError


class FraudModelMissingError(CrucibleError):
    """The trained fraud model artifact or its metadata is not on disk.

    Names the expected paths and the command to train it, so the fix is obvious.
    """
