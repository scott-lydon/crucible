"""Fix-durability audit: the tool red-teams its own fix. A durable (strong) fix
holds; a naive literal-only redaction is exposed as bypassable."""

from crucible.audit import fix_durability_audit
from crucible.sample_target import CANARY_SECRET, SampleTarget


def test_strong_redaction_is_durable():
    fixed = SampleTarget(guardrails=["secret_redact"])      # literal + transforms
    result = fix_durability_audit(fixed, [CANARY_SECRET])
    assert result["durable"] is True
    assert result["n_leaks"] == 0


def test_naive_redaction_is_bypassable_audit_has_teeth():
    naive = SampleTarget(guardrails=["secret_redact_naive"])  # literal only
    result = fix_durability_audit(naive, [CANARY_SECRET])
    assert result["durable"] is False                        # leaks via spaced/reversed/base64
    assert result["n_leaks"] > 0
