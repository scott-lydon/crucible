"""Slice 1c: the target suitability advisor.

Separate from the eligibility gate: eligibility asks "can this target run", suitability
asks "is it a GOOD FIT". It NEVER halts. It emits one warning line per concern, writes
suitability.json, and the run proceeds; the grade is printed in the report header so a
reader does not over-trust a POOR_FIT verdict.

It pairs deterministic signals (obligation / invariant count, which oracles actually
apply, task triviality) with the pre-baked warning shapes from the goal-loop checklist,
each carrying its "what happens if you run anyway". An LLM judgment can refine the grade
on real runs (the eval measures agreement with a labeled fit set); by default the
deterministic grade stands so the advisor spends nothing."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from orchestrator.wiring import Container, get_container
from shared.types.sealed_spec import SealedSpec

_TRIVIAL_HINTS = ("sum", "add two", "concatenate", "echo", "identity", "return the input")


class SuitabilityGrade(StrEnum):
    ideal = "IDEAL"
    workable = "WORKABLE"
    poor_fit = "POOR_FIT"


@dataclass(frozen=True)
class SuitabilityWarning:
    reason: str
    consequence_if_run_anyway: str
    mitigation: str


@dataclass(frozen=True)
class Suitability:
    grade: SuitabilityGrade
    target_kind: str
    warnings: list[SuitabilityWarning] = field(default_factory=list)
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "grade": str(self.grade),
            "target_kind": self.target_kind,
            "warnings": [asdict(w) for w in self.warnings],
            "signals": self.signals,
        }


def _substantive_obligations(spec: SealedSpec) -> int:
    # The positive "task" obligation is always present; the failure / hidden obligations
    # are what give the oracles something adversarial to check.
    return sum(1 for o in spec.obligations if o.obligation_id != "task")


def assess_suitability(
    target_kind: str, spec: SealedSpec, *, container: Container | None = None
) -> Suitability:
    container = container or get_container()
    warnings: list[SuitabilityWarning] = []

    n_oblig = _substantive_obligations(spec)
    n_invariants = len(spec.invariants)
    ensemble = [str(o.kind) for o in container.oracles_for(target_kind)]
    task_text = (spec.obligations[0].description.lower() if spec.obligations else "")
    trivial = any(hint in task_text for hint in _TRIVIAL_HINTS)

    signals = {
        "substantive_obligations": n_oblig,
        "invariants": n_invariants,
        "applicable_oracles": ensemble,
        "trivial_task": trivial,
    }

    if n_oblig <= 1 or n_invariants == 0:
        warnings.append(SuitabilityWarning(
            reason="few or no invariants / obligations to check",
            consequence_if_run_anyway=(
                "the oracles have little to check; a near-100% pass rate is uninformative, "
                "not evidence of correctness."),
            mitigation="add more failure_conditions / invariants so the panel has surface."))

    if target_kind in ("fraud", "dummy"):
        warnings.append(SuitabilityWarning(
            reason="Shape-1 classifier target",
            consequence_if_run_anyway=(
                "the four mechanical code oracles do not apply; the verdict rests on the "
                "judge plus score-threshold signals, so recall is softer than a code target's."),
            mitigation="treat the catch rate as a floor; add held-out partitions for truth."))

    if trivial:
        warnings.append(SuitabilityWarning(
            reason="trivial or closed-form task",
            consequence_if_run_anyway=(
                "the red agent has almost no surface to reward-hack, so a clean run does not "
                "show Crucible caught anything hard."),
            mitigation="point Crucible at a task with real failure modes to make it meaningful."))

    # Grade from the signals. Never halts regardless of grade.
    if n_oblig >= 3 and n_invariants >= 1 and len(ensemble) >= 4 and not trivial:
        grade = SuitabilityGrade.ideal
    elif n_oblig <= 1 or trivial:
        grade = SuitabilityGrade.poor_fit
    else:
        grade = SuitabilityGrade.workable

    return Suitability(grade, target_kind, warnings, signals)


# --- CLI handler (crucible suitability check ...) --------------------------
def cmd_suitability_check(args: argparse.Namespace) -> int:
    from crucible.specs import resolve_sealed_spec

    container = get_container()
    if args.target not in container.targets:
        print(json.dumps({"error": f"unknown target {args.target!r}; "
                          f"known: {sorted(container.targets)}"}, indent=2))
        return 1
    target = container.get_target(args.target)
    spec = resolve_sealed_spec(target, args.spec)
    suit = assess_suitability(args.target, spec, container=container)
    print(json.dumps(suit.to_dict(), indent=2))
    return 0   # suitability never fails the command (it never halts)
