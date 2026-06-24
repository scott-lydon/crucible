"""Typed identifiers.

Each identifier is a distinct frozen value object wrapping a string so that
passing a RunId where an AttackId is expected is a type error, not a runtime
surprise (coding-practices.md: "wrap primitives that could be confused").
The repetition is intentional: distinctness is the whole point.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Self

from .errors import DomainValidationError


def _require_nonempty(type_name: str, value: str) -> None:
    """Reject an empty identifier with a message that names the type."""
    if not value:
        raise DomainValidationError(
            f"{type_name} must be a non-empty string; got an empty value. "
            f"Generate one with {type_name}.new() or pass an existing id."
        )


@dataclass(frozen=True, slots=True)
class RunId:
    """Identifies one red-and-blue pass over a target."""

    value: str

    def __post_init__(self) -> None:
        _require_nonempty("RunId", self.value)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AttackId:
    """Identifies one red-agent attempt against the target."""

    value: str

    def __post_init__(self) -> None:
        _require_nonempty("AttackId", self.value)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class VerdictId:
    """Identifies one aggregated verdict over one submission."""

    value: str

    def __post_init__(self) -> None:
        _require_nonempty("VerdictId", self.value)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PatchId:
    """Identifies one blue-loop hardening patch."""

    value: str

    def __post_init__(self) -> None:
        _require_nonempty("PatchId", self.value)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class LlmCallId:
    """Identifies one large-language-model call, for the trace card."""

    value: str

    def __post_init__(self) -> None:
        _require_nonempty("LlmCallId", self.value)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SpecId:
    """Identifies one sealed specification version."""

    value: str

    def __post_init__(self) -> None:
        _require_nonempty("SpecId", self.value)

    @classmethod
    def new(cls) -> Self:
        return cls(uuid.uuid4().hex)

    def __str__(self) -> str:
        return self.value
