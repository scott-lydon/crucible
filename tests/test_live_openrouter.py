"""Live LLM tests against OpenRouter. DISABLED by default — they cost money.

Enable with:  CRUCIBLE_LIVE_LLM_TESTS=1 OPENROUTER_API_KEY=... pytest tests/test_live_openrouter.py
"""

import os

import pytest

_LIVE = os.environ.get("CRUCIBLE_LIVE_LLM_TESTS") == "1" and os.environ.get("OPENROUTER_API_KEY")
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="live LLM tests disabled (set CRUCIBLE_LIVE_LLM_TESTS=1 + OPENROUTER_API_KEY)")

from crucible.attacks import AttackEngine  # noqa: E402
from crucible.llm import OpenRouterLLM  # noqa: E402
from crucible.llm_target import LLMAgentTarget  # noqa: E402
from crucible.models import AttackClass  # noqa: E402
from crucible.oracles import OracleSuite  # noqa: E402
from crucible.profiler import profile_target  # noqa: E402


def test_openrouter_connectivity_and_cost_tracking():
    llm = OpenRouterLLM(model="anthropic/claude-3.5-haiku")
    assert llm.available
    assert llm.complete("Reply with one word.", "Say pong.", max_tokens=10)
    assert llm.n_calls == 1 and llm.cost >= 0


def test_real_llm_target_leak_is_ground_truth_verified():
    # llama-3.1-8b reliably leaks its system-prompt secret to public payloads
    llm = OpenRouterLLM(model="meta-llama/llama-3.1-8b-instruct")
    target = LLMAgentTarget(llm)
    profile = profile_target(target)
    findings = AttackEngine(target, OracleSuite(secrets=profile.secrets), seeds=1).run(
        [AttackClass.SECRET_EXFIL])
    assert any(f.proof.deterministic for f in findings)  # a real, canary-verified leak
