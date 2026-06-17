"""FixEngine — cluster findings by root cause, then for each vulnerability try
defense layers (structural first) in a sandbox until one closes the seen attacks
WITHOUT over-refusing benign traffic. Emits patches; never edits live."""

from __future__ import annotations

from typing import Any, Callable

from ..adapter import TargetAdapter
from ..evaluate import benign_pass_rate
from ..models import Finding, FixCandidate, Severity, Vulnerability
from ..oracles import OracleSuite
from ..profiler import TargetProfile
from .layers import ROOT_CAUSE, layer_order, propose

_SEV_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def merge_patch(dst: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    for g in patch.get("add_guardrails", []):
        dst.setdefault("add_guardrails", [])
        if g not in dst["add_guardrails"]:
            dst["add_guardrails"].append(g)
    for f in patch.get("add_input_filters", []):
        dst.setdefault("add_input_filters", []).append(f)
    if "tool_limits" in patch:
        dst.setdefault("tool_limits", {}).update(patch["tool_limits"])
    if "system_prompt" in patch:
        dst["system_prompt"] = patch["system_prompt"]
    return dst


class FixEngine:
    def __init__(
        self,
        target: TargetAdapter,
        oracles: OracleSuite,
        benign: list[str],
        prefer_structural: bool = True,
        max_rounds: int = 3,
        narrator: Callable[[str], None] | None = None,
    ):
        self.target = target
        self.oracles = oracles
        self.benign = benign
        self.prefer_structural = prefer_structural
        self.max_rounds = max_rounds
        self.narrate = narrator or (lambda _m: None)
        self._base_benign = benign_pass_rate(target, benign)

    def cluster(self, findings: list[Finding]) -> list[Vulnerability]:
        groups: dict[tuple, list[Finding]] = {}
        for f in findings:
            groups.setdefault((f.attack.attack_class, f.surface), []).append(f)
        vulns: list[Vulnerability] = []
        for i, ((cls, surface), fs) in enumerate(groups.items(), start=1):
            sev = max((f.severity for f in fs), key=_SEV_ORDER.index)
            vulns.append(
                Vulnerability(
                    id=f"V{i}", attack_class=cls, surface=surface,
                    root_cause=ROOT_CAUSE.get(cls, "unknown"), severity=sev, findings=fs,
                )
            )
        self.narrate(f"clustered {len(findings)} finding(s) into {len(vulns)} vulnerability(ies)")
        return vulns

    def fix(self, vulns: list[Vulnerability], profile: TargetProfile
            ) -> tuple[list[FixCandidate], dict[str, Any]]:
        merged: dict[str, Any] = {}
        candidates: list[FixCandidate] = []
        for v in vulns:
            seen = [f.attack.payload for f in v.findings]
            candidates.append(self._fix_one(v, seen, profile, merged))
        return candidates, merged

    def _fix_one(self, v: Vulnerability, seen: list[str], profile: TargetProfile,
                 merged: dict[str, Any]) -> FixCandidate:
        if self.target.clone_with_config(dict(merged)) is None:
            cand = propose(v, "prompt", seen, profile)
            cand.notes = "suggest-only (black-box target: cannot sandbox-verify the fix)"
            self.narrate(f"  • {v.id}: black-box → suggestion only")
            return cand

        last: FixCandidate | None = None
        for layer in layer_order(v.attack_class, self.prefer_structural)[: self.max_rounds]:
            cand = propose(v, layer, seen, profile)
            if cand is None:
                continue
            last = cand
            trial = merge_patch(dict(merged), cand.config_patch)
            sandbox = self.target.clone_with_config(trial)
            cand.rounds += 1
            cand.seen_pass = all(
                self.oracles.check(v.attack_class, sandbox.send(p)) is None for p in seen
            )
            cand.benign_pass = benign_pass_rate(sandbox, self.benign) >= self._base_benign
            if cand.seen_pass and cand.benign_pass:
                cand.accepted = True
                merge_patch(merged, cand.config_patch)
                self.narrate(f"  ✔ {v.id} fixed via [{layer}] — seen closed, benign preserved")
                return cand
            why = []
            if not cand.seen_pass:
                why.append("attack still works")
            if not cand.benign_pass:
                why.append("breaks benign (over-refusal)")
            self.narrate(f"  ↻ {v.id} [{layer}] rejected ({', '.join(why)}) → escalate")

        if last is not None:
            last.notes = ("could not verify a fix that closes the attack without over-refusal; "
                          "emitting best suggestion (graceful degradation)")
        return last  # type: ignore[return-value]
