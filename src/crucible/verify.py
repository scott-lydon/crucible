"""Ground-truth verification suite — measure Crucible against targets whose
vulnerabilities are KNOWN, so we can report recall (does it find the planted
holes?) and false-positive rate (does it stay quiet on the hardened ones?).

You can only grade a red-team tool against bugs you already know are there.
"""

from __future__ import annotations

from .attacks import AttackEngine
from .models import AttackClass
from .oracles import OracleSuite
from .profiler import profile_target
from .sample_target import SampleTarget

ALL = set(AttackClass)
PE, SE, TA, JB = (AttackClass.PROMPT_EXTRACTION, AttackClass.SECRET_EXFIL,
                  AttackClass.TOOL_ABUSE, AttackClass.JAILBREAK)

# (name, target factory, KNOWN-vulnerable classes)
GROUND_TRUTH = [
    ("vulnerable", lambda: SampleTarget(), {PE, SE, TA, JB}),
    ("secret_hardened", lambda: SampleTarget(guardrails=["secret_redact"]), {TA, JB}),
    ("tool_hardened", lambda: SampleTarget(tool_limits={"refund_max": 100}), {PE, SE, JB}),
    ("fully_hardened",
     lambda: SampleTarget(guardrails=["secret_redact", "forbidden_block"],
                          tool_limits={"refund_max": 100}), set()),
]


def detected_classes(target) -> set:
    profile = profile_target(target)
    oracles = OracleSuite(secrets=profile.secrets, refund_limit=profile.refund_limit)
    findings = AttackEngine(target, oracles, seeds=1).run(list(AttackClass))
    return {f.attack.attack_class for f in findings}


def measure(target, known: set) -> dict:
    found = detected_classes(target)
    not_vuln = ALL - known
    true_pos = found & known
    false_pos = found & not_vuln
    return {
        "found": sorted(c.value for c in found),
        "recall": (len(true_pos) / len(known)) if known else 1.0,
        "false_positive_rate": (len(false_pos) / len(not_vuln)) if not_vuln else 0.0,
        "false_positives": sorted(c.value for c in false_pos),
    }


def run_suite() -> dict:
    targets = {name: measure(factory(), known) for name, factory, known in GROUND_TRUTH}
    n = len(targets)
    return {
        "targets": targets,
        "macro_recall": round(sum(t["recall"] for t in targets.values()) / n, 3),
        "macro_false_positive_rate":
            round(sum(t["false_positive_rate"] for t in targets.values()) / n, 3),
    }
