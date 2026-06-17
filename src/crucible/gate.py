"""The single gate — the only stop in the loop. Present findings + the fix plan,
then decide whether to proceed. `auto` proceeds; `approve` waits for a human (or a
driving agent's `--yes`)."""

from __future__ import annotations

import sys
from typing import Callable

from .models import Finding, Vulnerability


def present(findings: list[Finding], vulns: list[Vulnerability],
            narrate: Callable[[str], None]) -> None:
    narrate("\n========== GATE: findings + fix plan ==========")
    if not findings:
        narrate("No confirmed vulnerabilities. Nothing to fix.")
        return
    by_class: dict[str, int] = {}
    for f in findings:
        by_class[f.attack.attack_class.value] = by_class.get(f.attack.attack_class.value, 0) + 1
    narrate(f"{len(findings)} confirmed finding(s) across {len(by_class)} class(es): "
            + ", ".join(f"{k}×{v}" for k, v in by_class.items()))
    for v in vulns:
        sample = v.findings[0]
        narrate(f"  • [{v.severity.value.upper()}] {v.id} {v.attack_class.value} "
                f"@ {v.surface}")
        narrate(f"      root cause: {v.root_cause}")
        narrate(f"      proof: {sample.proof.detail}")
    narrate("Proposed: cluster → strongest available defense layer → sandbox-verify "
            "(close attack + preserve benign) → emit diff (never live).")


def decide(mode: str, assume_yes: bool) -> bool:
    if mode == "auto" or assume_yes:
        return True
    if sys.stdin.isatty():
        return input("Proceed with fixes? [y/N] ").strip().lower() in ("y", "yes")
    return False
