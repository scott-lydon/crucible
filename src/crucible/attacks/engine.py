"""AttackEngine — expands the library via mutators, runs each attack against the
target across seeds, verifies with the oracle, and records wins to the catalog."""

from __future__ import annotations

from typing import Callable

from ..adapter import TargetAdapter
from ..models import Attack, AttackClass, Finding, Response, Severity
from ..oracles import OracleSuite
from .library import LIBRARY
from .mutators import ATTACK_MUTATORS, Mutator, expand

_SURFACE = {
    AttackClass.PROMPT_EXTRACTION: "system_prompt",
    AttackClass.SECRET_EXFIL: "system_prompt:secret",
    AttackClass.TOOL_ABUSE: "tool:refund",
    AttackClass.JAILBREAK: "output_policy",
}
_SEVERITY = {
    AttackClass.PROMPT_EXTRACTION: Severity.HIGH,
    AttackClass.SECRET_EXFIL: Severity.CRITICAL,
    AttackClass.TOOL_ABUSE: Severity.HIGH,
    AttackClass.JAILBREAK: Severity.MEDIUM,
}


class AttackEngine:
    def __init__(
        self,
        target: TargetAdapter,
        oracles: OracleSuite,
        catalog=None,
        seeds: int = 3,
        narrator: Callable[[str], None] | None = None,
        mutators: list[Mutator] | None = None,
    ):
        self.target = target
        self.oracles = oracles
        self.catalog = catalog
        self.seeds = max(1, seeds)
        self.narrate = narrator or (lambda _m: None)
        self.mutators = mutators or ATTACK_MUTATORS

    def run(self, classes: list[AttackClass]) -> list[Finding]:
        findings: list[Finding] = []
        for cls in classes:
            self.narrate(f"── class: {cls.value} ──")
            for atk in self._build_attacks(cls):
                self.narrate(f"  ⚔ trying [{atk.technique}] {atk.payload[:60]!r}")
                proof, response, succ_seed = self._run_attack(atk)
                if proof:
                    self.narrate(f"    ✗ BROKE IT → {proof.detail} "
                                 f"({'ground-truth' if proof.deterministic else 'judge'})")
                    findings.append(
                        Finding(
                            attack=atk,
                            response=response,
                            proof=proof,
                            severity=_SEVERITY[cls],
                            surface=_SURFACE[cls],
                            succeeded_seeds=succ_seed,
                            total_seeds=self.seeds,
                        )
                    )
                    if self.catalog is not None:
                        self.catalog.record_win(cls.value, atk.technique)
                else:
                    self.narrate("    ✓ held")
        self.narrate(f"attack phase complete: {len(findings)} confirmed finding(s)")
        return findings

    def _build_attacks(self, cls: AttackClass) -> list[Attack]:
        attacks: list[Attack] = []
        prioritized = set()
        if self.catalog is not None:
            prioritized = set(self.catalog.top_techniques(cls.value))
        items = expand(LIBRARY[cls], self.mutators)
        # techniques that won before float to the front (strategy catalog in action)
        items.sort(key=lambda it: 0 if it[1] in prioritized else 1)
        for i, (payload, tech, lineage) in enumerate(items):
            attacks.append(
                Attack(
                    id=f"{cls.value}-{i}",
                    attack_class=cls,
                    payload=payload,
                    technique=tech,
                    origin="catalog" if tech in prioritized else "mutation",
                    lineage=lineage,
                )
            )
        return attacks

    def _run_attack(self, atk: Attack) -> tuple[object, Response, int]:
        last = Response(text="")
        for seed in range(self.seeds):
            # seed perturbation is whitespace-only: no-op for intent, models real stochasticity
            resp = self.target.send(atk.payload + (" " * seed))
            last = resp
            proof = self.oracles.check(atk.attack_class, resp)
            if proof is not None:
                return proof, resp, seed + 1
        return None, last, 0
