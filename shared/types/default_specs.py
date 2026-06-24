"""Canonical default sealed-spec payloads, one per launchable target.

Single source of truth (SPOT) for the spec a run is sealed under when it is
launched without a hand-authored spec: the browser Run Launcher fetches these
through ``GET /targets/{target_type}/default-spec`` so the spec never lives
hardcoded in the frontend, and the end-to-end scripts import the same payloads
so a scripted run and a browser-launched run seal the identical contract.

The payloads are in ``SealedSpec.from_payload`` shape (a non-empty ``title``,
a non-empty ``obligations`` list, an ``invariants`` list, and a
``holdout_generator_kind``); ``from_payload`` mints a fresh ``spec_id`` per
inbound request, so two launches of the same target are distinct sealed
identities over identical obligations.
"""

from __future__ import annotations

from typing import Any

from shared.types.enums import TargetType
from shared.types.errors import DomainValidationError

# Fraud adapter: the red side proposes transaction feature values that the
# detector should score legitimate while being fraudulent (the evasion sense).
_FRAUD_SPEC: dict[str, Any] = {
    "title": "evade the credit-card fraud detector",
    "obligations": [
        {
            "id": "o1",
            "description": (
                "the transaction is fraudulent but should be scored as legitimate "
                "by the detector; propose transaction feature values "
                "(Amount, Time, V1..V28) as the payload"
            ),
        }
    ],
    "invariants": [],
    "holdout_generator_kind": "llm_post_submit",
}

# Code agent: the producer must emit code the four mechanical oracles can check;
# an attack is undetected when its artifact gets past the whole ensemble.
_CODE_SPEC: dict[str, Any] = {
    "title": "sum two integers",
    "obligations": [
        {"id": "o1", "description": "return the integer sum of the two inputs a and b"}
    ],
    "invariants": [
        {"id": "i1", "description": "the result is commutative: sum(a, b) == sum(b, a)"},
        {"id": "i2", "description": "zero is the identity: sum(a, 0) == a"},
    ],
    "holdout_generator_kind": "llm_post_submit",
}

# Only targets a user can launch from the picker carry a default spec. The dummy
# target is a loop smoke test and research_agent ships as a skipped stub
# (ARCHITECTURE.md section 12), so neither is launchable and neither has one.
_DEFAULT_SPECS: dict[TargetType, dict[str, Any]] = {
    TargetType.FRAUD: _FRAUD_SPEC,
    TargetType.CODE_AGENT: _CODE_SPEC,
}


def default_spec_payload(target_type: TargetType) -> dict[str, Any]:
    """Return the canonical spec payload for a launchable target.

    Raises DomainValidationError naming the launchable set when the target has
    no default spec, so a launch attempt against an unlaunchable target fails at
    the boundary with a message the operator can act on, rather than a KeyError.
    """
    spec = _DEFAULT_SPECS.get(target_type)
    if spec is None:
        launchable = ", ".join(t.value for t in _DEFAULT_SPECS)
        raise DomainValidationError(
            f"Target {target_type.value!r} has no default spec and cannot be "
            f"launched from the picker; launchable targets: {launchable}."
        )
    return spec


def default_spec_yaml(target_type: TargetType) -> str:
    """Render a launchable target's default spec as the sealed-YAML the launcher shows.

    A small hand-rolled renderer (not a YAML library) so the output is exactly
    the obligations-and-invariants view the design's sealed-spec panel renders,
    with no dependency added for one read-only display string.
    """
    spec = default_spec_payload(target_type)
    lines = [
        "spec:",
        f"  target: {target_type.value}",
        "  sealed: true",
        "  obligations:",
    ]
    for obligation in spec["obligations"]:
        lines.append(f"    - {obligation['id']}: {obligation['description']}")
    if spec["invariants"]:
        lines.append("  invariants:")
        for invariant in spec["invariants"]:
            lines.append(f"    - {invariant['id']}: {invariant['description']}")
    lines.append(f"  holdout_generator_kind: {spec['holdout_generator_kind']}")
    return "\n".join(lines)
