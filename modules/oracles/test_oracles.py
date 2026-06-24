import dataclasses
import json
import os
import pathlib
from typing import Protocol, cast

import pytest

from shared.types import (
    VerdictContext,
    OracleKind,
    OracleVote,
    Vote,
    SealedSpec,
    sealed_spec_from_dict,
    sealed_spec_from_yaml,
)
from shared.llm import AnthropicApiProvider, MockProvider
from examples.targets.fraud_synth import DETECTOR_THRESHOLD, Transaction, is_fraud
from modules.oracles.held_out.oracle import HeldOutOracle
from modules.oracles.metamorphic.oracle import MetamorphicOracle
from modules.oracles.invariant.oracle import InvariantOracle
from modules.oracles.differential.oracle import DifferentialOracle
from modules.oracles.property_fuzz.oracle import PropertyFuzzOracle
from modules.oracles.llm_judge.oracle import LlmJudgeOracle
from modules.oracles.aggregator import FAIL_THRESHOLD, aggregate
from hypothesis import strategies as st


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


# New structured judge payload: per-obligation findings + an independent
# lane-(b) finding + the final vote/reason.
_FAIL_JSON = json.dumps({
    "per_obligation": [{"id": "country_velocity_must_flag", "triggered": True,
                        "consistent": False}],
    "independent_finding": "pattern resembles a missed positive",
    "vote": "fail",
    "reason": "x",
})
_PASS_JSON = json.dumps({
    "per_obligation": [{"id": "country_velocity_must_flag", "triggered": False,
                        "consistent": True}],
    "independent_finding": "nothing suspicious",
    "vote": "pass",
    "reason": "looks clean",
})


def test_judge_parses_fail_with_half_weight_and_llm_evidence() -> None:
    provider = MockProvider(text=_FAIL_JSON)
    v = LlmJudgeOracle(provider=provider).vote(MISS_CTX)
    assert v.kind is OracleKind.LLM_JUDGE and v.vote is Vote.FAIL and v.weight == 0.5
    assert v.reason == "x"
    assert v.evidence.get("llm") is True
    assert v.evidence.get("model") == "mock"
    assert "input_tokens" in v.evidence and "output_tokens" in v.evidence
    assert "dollars" in v.evidence
    # Per-obligation findings + the independent lane-(b) finding are kept for audit.
    assert v.evidence.get("per_obligation") == [
        {"id": "country_velocity_must_flag", "triggered": True, "consistent": False}]
    assert v.evidence.get("independent_finding") == "pattern resembles a missed positive"


def test_judge_parses_pass_path() -> None:
    provider = MockProvider(text=_PASS_JSON)
    v = LlmJudgeOracle(provider=provider).vote(MISS_CTX)
    assert v.vote is Vote.PASS and v.weight == 0.5
    assert v.reason == "looks clean"
    assert v.evidence.get("independent_finding") == "nothing suspicious"


def test_judge_prompt_is_spec_driven_and_target_agnostic() -> None:
    # The prompt's target-specificity must come ENTIRELY from the injected spec
    # (data), never from hardcoded strings in the oracle. Build a tiny spec with
    # an invented invariant id and prove (1) that id flows into the prompt, and
    # (2) the oracle adds NO domain words of its own.
    spec = sealed_spec_from_dict({
        "target_kind": "anything",
        "obligations": [],
        "invariants": [{
            "name": "test_invariant_xyz",
            "description": "a generic invented rule",
            "kind": "must_flag_when",
            "params": {"all_of": []},
        }],
        "metamorphic_relations": [],
        "holdout_generator_kind": "deterministic_rule",
    })
    # A generic sample whose field names carry NO domain words, so any domain
    # word found in the prompt could only have been injected by the oracle.
    ctx = VerdictContext(
        sample=_GenericSample(f0=1.0, f1=0, f2=False),
        detector_score=0.1, threshold=DETECTOR_THRESHOLD, true_label=False,
        original_sample=None, original_score=None, spec=spec)

    captured = _PromptSpy(text=_PASS_JSON)
    LlmJudgeOracle(provider=captured).vote(ctx)  # type: ignore[arg-type]

    assert captured.prompt is not None
    # (1) spec data flows in: the invented id appears in the prompt.
    assert "test_invariant_xyz" in captured.prompt
    # (2) target-agnostic: NONE of the domain words appear in what the ORACLE
    # contributes. The spec and sample here are scrubbed of domain words, so any
    # hit would mean the oracle injected a hardcoded domain term.
    haystack = (captured.prompt + captured.system).lower()
    for word in ("fraud", "night", "hour", "amt", "amount", "velocity",
                 "country", "merchant", "category", "distance"):
        assert word not in haystack, f"oracle leaked domain word {word!r}"


class _CountingProvider:
    """Spy MockProvider: counts provider calls to prove the budget is honored."""

    def __init__(self, text: str) -> None:
        self._inner = MockProvider(text=text)
        self.calls = 0

    def complete(self, prompt: str, **kwargs: object) -> object:
        self.calls += 1
        return self._inner.complete(prompt, **kwargs)  # type: ignore[arg-type]


class _PromptSpy:
    """Captures the exact prompt/system passed to the provider for inspection."""

    def __init__(self, text: str) -> None:
        self._inner = MockProvider(text=text)
        self.prompt: str | None = None
        self.system: str = ""

    def complete(self, prompt: str, *, system: str | None = None,
                 **kwargs: object) -> object:
        self.prompt = prompt
        self.system = system or ""
        return self._inner.complete(prompt, system=system, **kwargs)  # type: ignore[arg-type]


@dataclasses.dataclass(frozen=True, slots=True)
class _GenericSample:
    """A sample whose field names carry no domain words (for the agnostic test)."""

    f0: float
    f1: int
    f2: bool


def test_judge_abstains_when_budget_exhausted() -> None:
    # With max_calls=1: first vote hits the provider; second abstains (weight 0)
    # with budget_exhausted evidence and does NOT touch the provider.
    provider = _CountingProvider(text=_FAIL_JSON)
    judge = LlmJudgeOracle(provider=provider, max_calls=1)  # type: ignore[arg-type]

    first = judge.vote(MISS_CTX)
    assert first.vote is Vote.FAIL and first.weight == 0.5
    assert provider.calls == 1

    second = judge.vote(MISS_CTX)
    assert second.vote is Vote.ABSTAIN and second.weight == 0.0
    assert second.evidence.get("budget_exhausted") is True
    assert second.evidence.get("llm") is True
    assert provider.calls == 1  # provider NOT called again


def test_judge_unbounded_by_default() -> None:
    # No max_calls -> unbounded: repeated votes always hit the provider.
    provider = _CountingProvider(text=_PASS_JSON)
    judge = LlmJudgeOracle(provider=provider)  # type: ignore[arg-type]
    for _ in range(3):
        assert judge.vote(MISS_CTX).vote is Vote.PASS
    assert provider.calls == 3


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


# --- property-fuzz oracle (slice-8): generative invariant-counterexample search ---

# A strategy generating Transactions across ranges that INCLUDE the invariant-
# satisfying region (country_mismatch true AND velocity > 5) at LOW amount, so a
# counterexample exists for an amt-reliant detector to be caught clearing.
def _txn_strategy() -> st.SearchStrategy[Transaction]:
    return st.builds(
        Transaction,
        txn_index=st.integers(min_value=0, max_value=1000),
        amount=st.floats(min_value=0.0, max_value=2000.0,
                         allow_nan=False, allow_infinity=False),
        velocity=st.integers(min_value=0, max_value=30),
        country_mismatch=st.booleans(),
        merchant_risk=st.floats(min_value=0.0, max_value=1.0,
                                allow_nan=False, allow_infinity=False),
        hour_of_day=st.integers(min_value=0, max_value=23),
    )


# Deliberately amt-reliant score_fn (mirrors the flawed detector's blind spot):
# only high `amount` clears the threshold; it ignores country/velocity. So a
# country_mismatch+high-velocity LOW-amount txn satisfies the must_flag invariant
# yet is cleared — exactly the counterexample the fuzzer must generate + shrink.
def _amt_only_score(sample: object) -> float:
    return 1.0 if cast(Transaction, sample).amount > 1000.0 else 0.0


def _ctx_for(spec: object, sample: object) -> VerdictContext:
    return VerdictContext(
        sample=sample, detector_score=0.0, threshold=0.5, true_label=True,
        original_sample=None, original_score=None, spec=cast(SealedSpec, spec))


def test_property_fuzz_generates_counterexample_on_flawed_detector() -> None:
    # slice-8 done-criteria: against an amt-reliant detector blind to
    # country/velocity, the fuzzer GENERATES an invariant-satisfying input
    # (country_mismatch true, velocity > 5) at low amt that the detector clears.
    oracle = PropertyFuzzOracle(
        score_fn=_amt_only_score, strategy=_txn_strategy(),
        max_examples=200, seed=8)
    v = oracle.vote(_ctx_for(SPEC, MISS_CTX.sample))
    assert v.kind is OracleKind.PROPERTY_FUZZ
    assert v.vote is Vote.FAIL and v.weight == 1.0
    assert v.evidence.get("invariant_id") == "country_velocity_must_flag"
    ce = cast(dict[str, object], v.evidence["counterexample"])
    # The counterexample MUST satisfy the invariant (the property's precondition).
    assert ce["country_mismatch"] is True and cast(int, ce["velocity"]) > 5
    # ...and have been cleared by the detector (score < threshold).
    assert cast(float, v.evidence["score"]) < 0.5


def test_property_fuzz_passes_when_detector_flags_all_invariant_inputs() -> None:
    # A score_fn that correctly flags EVERY invariant-satisfying input -> no
    # counterexample exists -> PASS at full weight.
    def correct_score(sample: object) -> float:
        txn = cast(Transaction, sample)
        return 1.0 if (txn.country_mismatch and txn.velocity > 5) else 0.0

    oracle = PropertyFuzzOracle(
        score_fn=correct_score, strategy=_txn_strategy(),
        max_examples=200, seed=8)
    v = oracle.vote(_ctx_for(SPEC, MISS_CTX.sample))
    assert v.vote is Vote.PASS and v.weight == 1.0
    assert v.evidence.get("run_level") is True


def test_property_fuzz_is_deterministic_same_seed_same_counterexample() -> None:
    # Same seed => byte-equal shrunk counterexample across two independent runs.
    def run() -> object:
        o = PropertyFuzzOracle(score_fn=_amt_only_score, strategy=_txn_strategy(),
                               max_examples=200, seed=8)
        return o.vote(_ctx_for(SPEC, MISS_CTX.sample)).evidence["counterexample"]

    assert run() == run()


def test_property_fuzz_memoizes_run_level_result() -> None:
    # The search is a property of the detector+spec, not of ctx.sample: a second
    # vote returns the SAME result without re-searching (examples_tried stable).
    calls = {"n": 0}

    def counting_score(sample: object) -> float:
        calls["n"] += 1
        return _amt_only_score(sample)

    oracle = PropertyFuzzOracle(score_fn=counting_score, strategy=_txn_strategy(),
                               max_examples=200, seed=8)
    first = oracle.vote(_ctx_for(SPEC, MISS_CTX.sample))
    after_first = calls["n"]
    second = oracle.vote(_ctx_for(SPEC, MISS_CTX.sample))
    assert calls["n"] == after_first  # provider/score_fn NOT touched again
    assert first.evidence["counterexample"] == second.evidence["counterexample"]


def test_aggregate_flags_missed_fraud() -> None:
    # Cross-family second opinion that flags the missed fraud -> differential
    # now contributes a 1.0 FAIL alongside held_out/metamorphic/invariant.
    oracles: list[_Oracle] = [HeldOutOracle(label_fn=is_fraud),
                              MetamorphicOracle(label_fn=is_fraud),
                              InvariantOracle(),
                              DifferentialOracle(second_opinion_is_fraud=lambda s: True),
                              PropertyFuzzOracle(
                                  score_fn=_amt_only_score, strategy=_txn_strategy(),
                                  max_examples=200, seed=8),
                              LlmJudgeOracle(
                                  provider=MockProvider(text=_FAIL_JSON))]
    verdict = aggregate([o.vote(MISS_CTX) for o in oracles])
    assert verdict.fail_weight >= FAIL_THRESHOLD
    assert verdict.aggregate_pass is False   # the detector's "clean" decision does NOT stand
