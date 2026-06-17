"""The thesis, in tests: structural fixes generalize; prompt-only fixes overfit
(held-out gap); the benign metric catches over-refusal."""

from crucible.attacks import AttackEngine
from crucible.config import ALL_CLASSES
from crucible.evaluate import EvalEngine, benign_pass_rate
from crucible.fix import FixEngine
from crucible.models import AttackClass
from crucible.oracles import OracleSuite
from crucible.profiler import profile_target
from crucible.sample_target import BENIGN_PROMPTS, SampleTarget

CLASSES = [AttackClass(c) for c in ALL_CLASSES]


def _attack(target):
    profile = profile_target(target)
    oracles = OracleSuite(secrets=profile.secrets, refund_limit=profile.refund_limit)
    findings = AttackEngine(target, oracles, seeds=1).run(CLASSES)
    return profile, oracles, findings


def _fix_and_eval(prefer_structural):
    target = SampleTarget()
    profile, oracles, findings = _attack(target)
    fixer = FixEngine(target, oracles, BENIGN_PROMPTS, prefer_structural=prefer_structural)
    vulns = fixer.cluster(findings)
    fixes, patch = fixer.fix(vulns, profile)
    fixed = target.clone_with_config(patch)
    ev = EvalEngine(oracles, BENIGN_PROMPTS).evaluate(target, fixed, findings, CLASSES)
    return fixes, ev


def test_structural_fix_generalizes():
    fixes, ev = _fix_and_eval(prefer_structural=True)
    assert ev.held_out_catch_rate >= 0.99          # generalizes to unseen variants
    assert abs(ev.generalization_gap) <= 0.01       # no memorization gap
    assert ev.utility_delta == 0.0                  # no over-refusal
    assert all(c.accepted for c in fixes)
    assert all(c.layer in ("guardrail", "tool_perm") for c in fixes)  # structural chosen


def test_prompt_only_fix_shows_generalization_gap():
    _fixes, ev = _fix_and_eval(prefer_structural=False)
    assert ev.seen_catch_rate >= 0.99               # blocks the exact attacks it saw
    assert ev.held_out_catch_rate < ev.seen_catch_rate  # ...but not fresh variants
    assert ev.generalization_gap > 0                # the overfit the held-out set exposes


def test_benign_metric_catches_over_refusal():
    target = SampleTarget()
    over = target.clone_with_config({"add_input_filters": ["refund"]})  # too broad
    assert benign_pass_rate(over, BENIGN_PROMPTS) < benign_pass_rate(target, BENIGN_PROMPTS)
