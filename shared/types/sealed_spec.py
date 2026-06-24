"""SealedSpec value object and its parts.

The task contract, sealed from the producer. Oracles read it through a
server-side resolver; the producer sandbox never sees it (ARCHITECTURE.md
section 11, the core bet). Slice 0 defines the shape and an API-payload
parser; the YAML loader and the Postgres-backed resolver land in slice 4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import DomainValidationError
from .ids import SpecId


@dataclass(frozen=True, slots=True)
class Obligation:
    """One machine-checkable requirement the producer output must satisfy."""

    id: str
    description: str

    def __post_init__(self) -> None:
        if not self.id or not self.description:
            raise DomainValidationError(
                f"Obligation needs a non-empty id and description; got "
                f"id={self.id!r}, description={self.description!r}."
            )


@dataclass(frozen=True, slots=True)
class Invariant:
    """A metamorphic or property relation.

    If the input changes one way, the output must change a prescribed way.
    The metamorphic and property-fuzz oracles derive checks from these.
    """

    id: str
    description: str

    def __post_init__(self) -> None:
        if not self.id or not self.description:
            raise DomainValidationError(
                f"Invariant needs a non-empty id and description; got "
                f"id={self.id!r}, description={self.description!r}."
            )


@dataclass(frozen=True, slots=True)
class SealedSpec:
    """A sealed task contract the oracles check the producer against."""

    spec_id: SpecId
    title: str
    obligations: tuple[Obligation, ...]
    invariants: tuple[Invariant, ...]
    holdout_generator_kind: str

    def __post_init__(self) -> None:
        if not self.title:
            raise DomainValidationError("SealedSpec.title must be non-empty.")
        if not self.obligations:
            raise DomainValidationError(
                "SealedSpec must declare at least one obligation; a spec with no "
                "obligations gives the oracles nothing to check against."
            )

    def as_json(self) -> dict[str, Any]:
        """Serialize for the `runs.spec_json` JSONB column and the dashboard."""
        return {
            "spec_id": self.spec_id.value,
            "title": self.title,
            "obligations": [{"id": o.id, "description": o.description} for o in self.obligations],
            "invariants": [{"id": i.id, "description": i.description} for i in self.invariants],
            "holdout_generator_kind": self.holdout_generator_kind,
        }

    @classmethod
    def from_stored(cls, data: dict[str, Any]) -> SealedSpec:
        """Rebuild a SealedSpec from its stored `as_json` form, preserving spec_id.

        Used by the server-side resolver, so a spec read back from Postgres is
        the same identity it was sealed under (unlike from_payload, which mints a
        fresh id for inbound API requests).
        """
        return cls(
            spec_id=SpecId(str(data["spec_id"])),
            title=str(data["title"]),
            obligations=tuple(
                Obligation(id=str(o["id"]), description=str(o["description"]))
                for o in data["obligations"]
            ),
            invariants=tuple(
                Invariant(id=str(i["id"]), description=str(i["description"]))
                for i in data.get("invariants", [])
            ),
            holdout_generator_kind=str(data["holdout_generator_kind"]),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> SealedSpec:
        """Parse an API request body into a SealedSpec (parse, do not validate).

        Raises DomainValidationError with the offending field when the shape is
        wrong, so a malformed POST /runs body fails at the boundary with a
        message naming exactly what was missing.
        """
        title = payload.get("title")
        if not isinstance(title, str) or not title:
            raise DomainValidationError(
                "Spec payload needs a non-empty string 'title'; "
                f"got {title!r}."
            )
        raw_obligations = payload.get("obligations", [])
        if not isinstance(raw_obligations, list) or not raw_obligations:
            raise DomainValidationError(
                "Spec payload needs a non-empty list 'obligations'; "
                f"got {raw_obligations!r}."
            )
        obligations = tuple(
            Obligation(id=str(o["id"]), description=str(o["description"]))
            for o in raw_obligations
        )
        raw_invariants = payload.get("invariants", [])
        if not isinstance(raw_invariants, list):
            raise DomainValidationError(
                f"Spec payload 'invariants' must be a list; got {raw_invariants!r}."
            )
        invariants = tuple(
            Invariant(id=str(i["id"]), description=str(i["description"]))
            for i in raw_invariants
        )
        holdout_kind = str(payload.get("holdout_generator_kind", "llm_post_submit"))
        return cls(
            spec_id=SpecId.new(),
            title=title,
            obligations=obligations,
            invariants=invariants,
            holdout_generator_kind=holdout_kind,
        )
