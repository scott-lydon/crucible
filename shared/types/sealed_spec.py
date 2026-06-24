"""SealedSpec: the typed declaration of what a target must satisfy.

A SealedSpec expresses obligations, invariants, and metamorphic relations as
DATA, so an oracle engine can eventually evaluate them without hardcoding
target-specific logic. This module defines the value objects and boundary-
validating loaders (`from_dict` / `from_yaml`); it does not evaluate anything.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import yaml


@dataclass(frozen=True, slots=True)
class Invariant:
    """A hard rule the target must satisfy, expressed declaratively so an oracle
    engine can evaluate it without hardcoding target-specific logic."""

    name: str
    description: str
    kind: str  # e.g. "must_flag_when"
    params: Mapping[str, object]  # e.g. {"all_of": [{"feature": ..., "gt": 5}]}


@dataclass(frozen=True, slots=True)
class MetamorphicRelation:
    """If you mutate `feature` in `direction`, the true label must (or must not)
    change."""

    name: str
    description: str
    feature: str  # e.g. "amount"
    direction: str  # "decrease" | "increase"
    label_must_change: bool  # False = mutation must NOT change the true label


@dataclass(frozen=True, slots=True)
class SealedSpec:
    target_kind: str  # e.g. "fraud"
    obligations: tuple[str, ...]
    invariants: tuple[Invariant, ...]
    metamorphic_relations: tuple[MetamorphicRelation, ...]
    holdout_generator_kind: str


def _require(data: Mapping[str, object], key: str, ctx: str) -> object:
    if key not in data:
        raise ValueError(f"{ctx}: missing required key {key!r}")
    return data[key]


def _require_str(data: Mapping[str, object], key: str, ctx: str) -> str:
    value = _require(data, key, ctx)
    if not isinstance(value, str):
        raise ValueError(f"{ctx}: key {key!r} must be a str, got {type(value).__name__}")
    return value


def _require_bool(data: Mapping[str, object], key: str, ctx: str) -> bool:
    value = _require(data, key, ctx)
    # Reject ints masquerading as bools (bool is a subclass of int).
    if not isinstance(value, bool):
        raise ValueError(f"{ctx}: key {key!r} must be a bool, got {type(value).__name__}")
    return value


def _require_list(data: Mapping[str, object], key: str, ctx: str) -> list[object]:
    value = _require(data, key, ctx)
    if not isinstance(value, list):
        raise ValueError(f"{ctx}: key {key!r} must be a list, got {type(value).__name__}")
    return value


def _require_mapping(value: object, ctx: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{ctx}: expected a mapping, got {type(value).__name__}")
    return value


def _invariant_from_dict(data: Mapping[str, object]) -> Invariant:
    ctx = "invariant"
    params = _require(data, "params", ctx)
    if not isinstance(params, Mapping):
        raise ValueError(f"{ctx}: key 'params' must be a mapping, got {type(params).__name__}")
    return Invariant(
        name=_require_str(data, "name", ctx),
        description=_require_str(data, "description", ctx),
        kind=_require_str(data, "kind", ctx),
        params=dict(params),
    )


def _metamorphic_from_dict(data: Mapping[str, object]) -> MetamorphicRelation:
    ctx = "metamorphic_relation"
    return MetamorphicRelation(
        name=_require_str(data, "name", ctx),
        description=_require_str(data, "description", ctx),
        feature=_require_str(data, "feature", ctx),
        direction=_require_str(data, "direction", ctx),
        label_must_change=_require_bool(data, "label_must_change", ctx),
    )


def from_dict(data: Mapping[str, object]) -> SealedSpec:
    """Build a SealedSpec from a plain mapping, validating at the boundary.

    Raises ValueError (never KeyError, never a silent default) if a required key
    is missing or a field has the wrong type. Nested invariant/metamorphic dicts
    are coerced into their typed tuples.
    """
    ctx = "sealed_spec"
    if not isinstance(data, Mapping):
        raise ValueError(f"{ctx}: expected a mapping, got {type(data).__name__}")

    obligations_raw = _require_list(data, "obligations", ctx)
    obligations: list[str] = []
    for i, item in enumerate(obligations_raw):
        if not isinstance(item, str):
            raise ValueError(
                f"{ctx}: obligations[{i}] must be a str, got {type(item).__name__}"
            )
        obligations.append(item)

    invariants_raw = _require_list(data, "invariants", ctx)
    invariants = tuple(
        _invariant_from_dict(_require_mapping(item, f"{ctx}.invariants[{i}]"))
        for i, item in enumerate(invariants_raw)
    )

    metamorphic_raw = _require_list(data, "metamorphic_relations", ctx)
    metamorphic = tuple(
        _metamorphic_from_dict(_require_mapping(item, f"{ctx}.metamorphic_relations[{i}]"))
        for i, item in enumerate(metamorphic_raw)
    )

    return SealedSpec(
        target_kind=_require_str(data, "target_kind", ctx),
        obligations=tuple(obligations),
        invariants=invariants,
        metamorphic_relations=metamorphic,
        holdout_generator_kind=_require_str(data, "holdout_generator_kind", ctx),
    )


def from_yaml(text: str) -> SealedSpec:
    """Parse YAML (via yaml.safe_load) and build a SealedSpec from it.

    A malformed-YAML input (e.g. a syntax error from the operator's pasted spec)
    is normalized to ``ValueError`` — the same "bad input" type every structural
    failure below raises — so the one validating loader is the SINGLE point that
    signals an invalid spec. Callers (``create_run``) translate that ``ValueError``
    into a typed 422 at the boundary; a YAML parse error must not escape as a 500.
    """
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"sealed_spec: invalid YAML: {exc}") from exc
    if not isinstance(loaded, Mapping):
        raise ValueError(
            f"sealed_spec: YAML must parse to a mapping, got {type(loaded).__name__}"
        )
    return from_dict(loaded)


def to_dict(spec: SealedSpec) -> dict[str, object]:
    """Serialize a SealedSpec to a plain JSON-safe mapping.

    The inverse of :func:`from_dict`: ``from_dict(to_dict(spec)) == spec``. Used
    to persist the sealed spec as JSON (e.g. in the Postgres ``specs`` table) so
    the server-side resolver can rehydrate it without re-reading YAML from disk.
    """
    return {
        "target_kind": spec.target_kind,
        "obligations": list(spec.obligations),
        "invariants": [
            {
                "name": inv.name,
                "description": inv.description,
                "kind": inv.kind,
                "params": dict(inv.params),
            }
            for inv in spec.invariants
        ],
        "metamorphic_relations": [
            {
                "name": rel.name,
                "description": rel.description,
                "feature": rel.feature,
                "direction": rel.direction,
                "label_must_change": rel.label_must_change,
            }
            for rel in spec.metamorphic_relations
        ],
        "holdout_generator_kind": spec.holdout_generator_kind,
    }
