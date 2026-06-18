from crucible.attacks import ATTACK_MUTATORS, HELDOUT_MUTATORS, AttackEngine, expand
from crucible.attacks.library import LIBRARY
from crucible.models import AttackClass
from crucible.oracles import OracleSuite
from crucible.profiler import profile_target
from crucible.sample_target import SampleTarget


def test_engine_finds_all_four_classes():
    target = SampleTarget()
    profile = profile_target(target)
    oracles = OracleSuite(secrets=profile.secrets, refund_limit=profile.refund_limit)
    engine = AttackEngine(target, oracles, seeds=1)
    findings = engine.run(list(AttackClass))
    found_classes = {f.attack.attack_class for f in findings}
    assert found_classes == set(AttackClass)
    assert all(f.proof.deterministic for f in findings)  # all v1 oracles are ground-truth


def test_attack_and_heldout_operator_sets_are_disjoint():
    a = {m(LIBRARY[AttackClass.JAILBREAK][0])[1] for m in ATTACK_MUTATORS}
    h = {m(LIBRARY[AttackClass.JAILBREAK][0])[1] for m in HELDOUT_MUTATORS}
    assert a.isdisjoint(h)  # the firewall: held-out uses fresh techniques


def test_indirect_injection_via_content_is_caught():
    target = SampleTarget()
    profile = profile_target(target)
    oracles = OracleSuite(secrets=profile.secrets, refund_limit=profile.refund_limit)
    findings = AttackEngine(target, oracles, seeds=1).run([AttackClass.INDIRECT_INJECTION])
    assert findings  # instructions hidden in processed content leak the canary
    assert all(f.surface == "untrusted_content" for f in findings)


def test_profiler_reads_grey_box_config():
    p = profile_target(SampleTarget())
    assert p.access == "grey-box"
    assert p.secrets and p.system_prompt
