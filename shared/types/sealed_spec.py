"""The sealed specification: obligations and invariants the producer must satisfy.

"Sealed" is a runtime property (the producer container cannot reach this object via
the server-side resolver), not a property of the dataclass. See constitution.md
section 3 and docs/VOCABULARY.md ("Sealed specification")."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import yaml

from shared.types.enums import Shape


@dataclass(frozen=True, slots=True)
class Obligation:
    """One thing the producer must do. Oracles cite ``description`` verbatim."""

    obligation_id: str
    description: str
    check_kind: str               # oracle hint, e.g. "label_match" | "monotonic" | "no_hardcode"
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Invariant:
    """A relation that must always hold; consumed by property-fuzz and metamorphic."""

    invariant_id: str
    description: str
    expression: str               # e.g. "amount >= 0"


@dataclass(frozen=True, slots=True)
class SealedSpec:
    spec_id: str
    target_kind: str
    shape: Shape
    obligations: tuple[Obligation, ...]
    invariants: tuple[Invariant, ...]
    holdout_generator_kind: str   # "data_partition" (Shape 1) | "llm_generated" (Shape 2)

    def obligation_text(self, check_kind: str | None = None) -> str:
        """The verbatim obligation an oracle cites. Prefers the obligation matching
        ``check_kind``; falls back to the first declared obligation."""
        if check_kind is not None:
            for obligation in self.obligations:
                if obligation.check_kind == check_kind:
                    return obligation.description
        return self.obligations[0].description if self.obligations else "(no obligation declared)"

    def to_dict(self) -> dict[str, Any]:
        """Full serialization for the ``specs`` table, so the server-side resolver
        can rehydrate the spec without re-parsing YAML."""
        return {
            "spec_id": self.spec_id,
            "target_kind": self.target_kind,
            "shape": str(self.shape),
            "holdout_generator_kind": self.holdout_generator_kind,
            "obligations": [
                {
                    "id": o.obligation_id,
                    "description": o.description,
                    "check_kind": o.check_kind,
                    "params": dict(o.params),
                }
                for o in self.obligations
            ],
            "invariants": [
                {"id": i.invariant_id, "description": i.description, "expression": i.expression}
                for i in self.invariants
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SealedSpec:
        obligations = tuple(
            Obligation(
                obligation_id=str(o["id"]),
                description=str(o["description"]),
                check_kind=str(o["check_kind"]),
                params=dict(o.get("params", {})),
            )
            for o in raw.get("obligations", [])
        )
        invariants = tuple(
            Invariant(
                invariant_id=str(i["id"]),
                description=str(i["description"]),
                expression=str(i["expression"]),
            )
            for i in raw.get("invariants", [])
        )
        return cls(
            spec_id=str(raw["spec_id"]),
            target_kind=str(raw["target_kind"]),
            shape=Shape(raw["shape"]),
            obligations=obligations,
            invariants=invariants,
            holdout_generator_kind=str(raw["holdout_generator_kind"]),
        )

    @classmethod
    def from_yaml(cls, text: str) -> SealedSpec:
        """Parse the YAML an operator pastes into the Run Launcher.

        Fails loud (KeyError / ValueError) on a malformed spec — never silently
        defaults, per constitution.md section 8.
        """
        raw = cast("dict[str, Any]", yaml.safe_load(text))
        if not isinstance(raw, dict):
            raise ValueError("sealed spec must be a YAML mapping")
        return cls.from_dict(raw)
