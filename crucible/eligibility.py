"""Slice 1b: the target eligibility pre-flight gate.

``check_eligibility`` runs BEFORE any LLM spend and classifies a target as ELIGIBLE,
ELIGIBLE_WITH_CAVEAT, or INELIGIBLE. It reuses the existing adapter registry (the wired
container) and the targets' own health self-tests; it adds no new verification logic. On
INELIGIBLE the run is rejected and exits non-zero without spending a cent on the loop."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from crucible.runtime import docker_running, target_needs_docker
from orchestrator.wiring import Container, get_container
from shared.types.sealed_spec import SealedSpec

_KNOWN_HOLDOUT_KINDS = frozenset({"data_partition", "llm_generated"})


class EligibilityVerdict(StrEnum):
    eligible = "ELIGIBLE"
    eligible_with_caveat = "ELIGIBLE_WITH_CAVEAT"
    ineligible = "INELIGIBLE"


@dataclass(frozen=True)
class EligibilityReason:
    code: str            # machine-stable reason code
    message: str         # what is wrong
    fix: str             # the exact fix


@dataclass(frozen=True)
class Eligibility:
    verdict: EligibilityVerdict
    target_kind: str
    reasons: list[EligibilityReason] = field(default_factory=list)
    ensemble: list[str] = field(default_factory=list)   # oracles that will actually vote
    caveats: list[str] = field(default_factory=list)

    @property
    def is_ineligible(self) -> bool:
        return self.verdict is EligibilityVerdict.ineligible

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": str(self.verdict),
            "target_kind": self.target_kind,
            "reasons": [asdict(r) for r in self.reasons],
            "ensemble": self.ensemble,
            "caveats": self.caveats,
        }


def _spec_reasons(target_kind: str, spec: SealedSpec) -> list[EligibilityReason]:
    reasons: list[EligibilityReason] = []
    if not spec.obligations:
        reasons.append(EligibilityReason(
            "spec_no_obligations", "spec has zero obligations; oracles cannot be derived",
            "Add at least one obligation (or one failure_condition the compiler turns into one)."))
    if spec.holdout_generator_kind not in _KNOWN_HOLDOUT_KINDS:
        reasons.append(EligibilityReason(
            "spec_unknown_holdout",
            f"unknown holdout_generator_kind {spec.holdout_generator_kind!r}",
            f"Use one of {sorted(_KNOWN_HOLDOUT_KINDS)}."))
    if spec.target_kind and spec.target_kind != target_kind:
        reasons.append(EligibilityReason(
            "spec_target_mismatch",
            f"spec.target_kind={spec.target_kind!r} but chosen target is {target_kind!r}",
            "Point --target at the spec's target_kind, or fix the spec."))
    return reasons


def check_eligibility(
    target_kind: str, spec: SealedSpec, *, container: Container | None = None
) -> Eligibility:
    """Classify the target. Reuses the container's registry + the target health probe."""
    container = container or get_container()
    reasons: list[EligibilityReason] = []

    if target_kind not in container.targets:
        return Eligibility(
            EligibilityVerdict.ineligible, target_kind,
            [EligibilityReason(
                "unknown_target", f"no adapter registered for target {target_kind!r}",
                f"Register an adapter (crucible adapter scaffold ...) or pick one of "
                f"{sorted(container.targets)}.")])

    target = container.get_target(target_kind)
    reasons.extend(_spec_reasons(target_kind, spec))

    # Reuse the target's own health self-test (the same probe the /health route walks).
    health = asyncio.run(target.health())
    if health.status == "stub":
        reasons.append(EligibilityReason(
            "target_stub", f"target {target_kind!r} is a stub (health=stub)",
            "Implement the adapter's submit()/health() so it returns real output."))
    elif health.status in ("red", "amber"):
        reasons.append(EligibilityReason(
            "target_unhealthy",
            f"target health is {health.status}: {health.error or 'self-test failed'}",
            "Fix the target: the artifact/model may be missing or the endpoint unreachable "
            "(e.g. train the .lgb, or start the endpoint)."))

    # Code-shaped targets execute the producer in the Docker sandbox.
    if target_needs_docker(target_kind):
        docker = docker_running()
        if not docker.ok:
            reasons.append(EligibilityReason(
                "sandbox_unavailable", f"producer sandbox runtime unavailable: {docker.detail}",
                docker.fix))

    if reasons:
        return Eligibility(EligibilityVerdict.ineligible, target_kind, reasons)

    ensemble = [str(o.kind) for o in container.oracles_for(target_kind)]
    # Shape-1 classifiers: the verdict leans on the judge + score-threshold signals and is
    # softer than a code target's; state it up front so a thin verdict is not a surprise.
    caveats: list[str] = []
    verdict = EligibilityVerdict.eligible
    shape = getattr(target, "shape", None)
    if shape is not None and str(shape) == "shape1_ml":
        verdict = EligibilityVerdict.eligible_with_caveat
        caveats.append(
            "Shape-1 classifier: the verdict rests on the judge plus score-threshold "
            "signals; recall is softer than a code target's.")
    return Eligibility(verdict, target_kind, [], ensemble, caveats)


# --- CLI handler (crucible eligibility check ...) --------------------------
def cmd_eligibility_check(args: argparse.Namespace) -> int:
    from crucible.specs import resolve_sealed_spec

    container = get_container()
    if args.target not in container.targets:
        elig = check_eligibility(args.target, _empty_spec(args.target), container=container)
    else:
        target = container.get_target(args.target)
        try:
            spec = resolve_sealed_spec(target, args.spec)
        except Exception as exc:  # noqa: BLE001
            elig = Eligibility(
                EligibilityVerdict.ineligible, args.target,
                [EligibilityReason("spec_unparseable", str(exc), "Provide a valid --spec YAML.")])
            print(json.dumps(elig.to_dict(), indent=2))
            return 1
        elig = check_eligibility(args.target, spec, container=container)
    print(json.dumps(elig.to_dict(), indent=2))
    return 1 if elig.is_ineligible else 0


def _empty_spec(target_kind: str) -> SealedSpec:
    from shared.types.enums import Shape

    return SealedSpec(
        spec_id="none", target_kind=target_kind, shape=Shape.shape2_agent,
        obligations=(), invariants=(), holdout_generator_kind="llm_generated")
