import os
import pathlib
from typing import Protocol

import pytest

from shared.types import (
    VerdictContext,
    OracleKind,
    OracleVote,
    Vote,
    sealed_spec_from_yaml,
)
from shared.llm import AnthropicApiProvider, MockProvider
from examples.targets.fraud_synth import DETECTOR_THRESHOLD, Transaction, is_fraud
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential.oracle import DifferentialOracle
from modules.oracles.llm_judge.oracle import LlmJudgeOracle
from modules.oracles.aggregator import FAIL_THRESHOLD, aggregate


class _Oracle(Protocol):
    def vote(self, ctx: VerdictContext) -> OracleVote: ...


_SPEC_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "specs" / "fraud_v0.yaml"
)
SPEC = sealed_spec_from_yaml(_SPEC_PATH.read_text())

# a cleared (score < threshold) transaction that is truly fraud (velocity) = a MISS,
# whose amount was lowered from a previously-caught variant (R1 evasion).
MISS_CTX = VerdictContext(
    sample=Transaction(0, amount=12.0, velocity=12, country_mismatch=True,
                       merchant_risk=0.2, hour_of_day=4),
    detector_score=0.2, threshold=DETECTOR_THRESHOLD, true_label=True,
    original_sample=Transaction(0, amount=1500.0, velocity=12, country_mismatch=True,
                                merchant_risk=0.2, hour_of_day=2),
    original_score=0.8,
    spec=SPEC)


def test_held_out_fails_on_missed_fraud() -> None:
    v = HeldOutOracle(label_fn=is_fraud).vote(MISS_CTX)
    assert v.kind is OracleKind.HELD_OUT and v.vote is Vote.FAIL and v.weight == 1.0


def test_metamorphic_detects_amount_lowering_evasion() -> None:
    v = MetamorphicOracle(label_fn=is_fraud).vote(MISS_CTX)   # big score drop, label unchanged
    assert v.vote is Vote.FAIL and v.weight == 1.0


def test_invariant_fires_on_country_velocity() -> None:
    v = InvariantOracle().vote(MISS_CTX)
    assert v.vote is Vote.FAIL and v.weight == 1.0


def test_differential_fails_when_cross_family_flags_cleared_fraud() -> None:
    # A cross-family second opinion that flags fraud the target CLEARED (MISS_CTX
    # is a cleared, truly-fraud sample) must FAIL with full weight.
    v = DifferentialOracle(second_opinion_is_fraud=lambda s: True).vote(MISS_CTX)
    assert v.kind is OracleKind.DIFFERENTIAL and v.vote is Vote.FAIL and v.weight == 1.0


def test_differential_abstains_without_second_opinion() -> None:
    # No second-family model wired -> honest ABSTAIN at weight 0 (not a stub).
    v = DifferentialOracle().vote(MISS_CTX)
    assert v.kind is OracleKind.DIFFERENTIAL and v.vote is Vote.ABSTAIN and v.weight == 0.0


def test_judge_parses_fail_with_half_weight_and_llm_evidence() -> None:
    provider = MockProvider(text='{"vote": "fail", "reason": "x"}')
    v = LlmJudgeOracle(provider=provider).vote(MISS_CTX)
    assert v.kind is OracleKind.LLM_JUDGE and v.vote is Vote.FAIL and v.weight == 0.5
    assert v.reason == "x"
    assert v.evidence.get("llm") is True
    assert v.evidence.get("model") == "mock"
    assert "input_tokens" in v.evidence and "output_tokens" in v.evidence
    assert "dollars" in v.evidence


def test_judge_parses_pass_path() -> None:
    provider = MockProvider(text='{"vote": "pass", "reason": "looks clean"}')
    v = LlmJudgeOracle(provider=provider).vote(MISS_CTX)
    assert v.vote is Vote.PASS and v.weight == 0.5
    assert v.reason == "looks clean"


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="no ANTHROPIC_API_KEY",
)
def test_judge_live_opus_one_call() -> None:
    # The only test here that costs money: ONE real Opus 4.8 call.
    v = LlmJudgeOracle(provider=AnthropicApiProvider()).vote(MISS_CTX)
    assert v.kind is OracleKind.LLM_JUDGE and v.weight == 0.5
    assert v.vote in (Vote.PASS, Vote.FAIL)
    assert v.evidence.get("llm") is True
    assert isinstance(v.evidence.get("dollars"), float)
    assert v.evidence["dollars"] > 0  # type: ignore[operator]


def test_aggregate_flags_missed_fraud() -> None:
    # Cross-family second opinion that flags the missed fraud -> differential
    # now contributes a 1.0 FAIL alongside held_out/metamorphic/invariant.
    oracles: list[_Oracle] = [HeldOutOracle(label_fn=is_fraud),
                              MetamorphicOracle(label_fn=is_fraud),
                              InvariantOracle(),
                              DifferentialOracle(second_opinion_is_fraud=lambda s: True),
                              LlmJudgeOracle(
                                  provider=MockProvider(
                                      text='{"vote": "fail", "reason": "x"}'))]
    verdict = aggregate([o.vote(MISS_CTX) for o in oracles])
    assert verdict.fail_weight >= FAIL_THRESHOLD
    assert verdict.aggregate_pass is False   # the detector's "clean" decision does NOT stand
