"""Unit tests for the LLM red agent — fully offline via MockProvider."""

import os
from dataclasses import dataclass

import pytest

from shared.llm import AnthropicApiProvider, MockProvider
from shared.types import sealed_spec_from_yaml

from modules.red.catalog import StrategyCatalog
from modules.red.llm_red.agent import LlmRedAdversary

_SPEC = sealed_spec_from_yaml(
    """
target_kind: fraud
obligations:
  - flag truly fraudulent transactions
invariants: []
metamorphic_relations:
  - name: amt_decrease_label_invariance
    description: Lowering amount does not change the true fraud label.
    feature: amt
    direction: decrease
    label_must_change: false
holdout_generator_kind: deterministic_real_sample
"""
)


@dataclass(frozen=True, slots=True)
class _Txn:
    txn_index: int
    amt: float
    merchant_risk: float
    hour: int


def _score_high_amt(sample: object) -> float:
    # Amount-reliant detector: clears once amt is small.
    return 0.9 if getattr(sample, "amt") > 100.0 else 0.1


def _is_fraud_night(sample: object) -> bool:
    # Night-hour fraud regardless of amount: lowering amt preserves the label.
    return getattr(sample, "hour") in {0, 1, 2, 3}


def test_mutate_returns_mutated_sample_and_records_catalog() -> None:
    catalog = StrategyCatalog()
    adv = LlmRedAdversary(
        provider=MockProvider(
            text='{"moves":[{"feature":"amt","new_value":1.0}],"rationale":"x"}'
        ),
        spec=_SPEC,
        score_fn=_score_high_amt,
        label_fn=_is_fraud_night,
        threshold=0.5,
        catalog=catalog,
    )
    caught = _Txn(txn_index=0, amt=1500.0, merchant_risk=0.9, hour=2)

    out = adv.mutate(caught, _score_high_amt(caught))

    assert out is not None
    assert getattr(out, "amt") == 1.0
    assert _is_fraud_night(out) is True
    assert _score_high_amt(out) < 0.5
    assert adv.calls_made == 1
    assert catalog.summary() == [
        {"feature": "amt", "direction": "decrease", "source": "llm", "count": 1}
    ]


def test_mutate_lands_multi_feature_evasion_and_records_each_move() -> None:
    # FREE multi-feature: a detector that clears only when BOTH amt is small AND
    # merchant_risk is lowered. A single-axis red could never land this; the LLM
    # red combines two features in one proposal. Proves >amt evasion.
    def _score_two_axis(sample: object) -> float:
        amt = getattr(sample, "amt")
        risk = getattr(sample, "merchant_risk")
        return 0.1 if (amt <= 100.0 and risk <= 0.3) else 0.9

    catalog = StrategyCatalog()
    adv = LlmRedAdversary(
        provider=MockProvider(
            text='{"moves":[{"feature":"amt","new_value":50.0},'
            '{"feature":"merchant_risk","new_value":0.1}],"rationale":"combine"}'
        ),
        spec=_SPEC,
        score_fn=_score_two_axis,
        label_fn=_is_fraud_night,
        threshold=0.5,
        movable_features=["amt", "merchant_risk"],
        catalog=catalog,
    )
    caught = _Txn(txn_index=0, amt=1500.0, merchant_risk=0.9, hour=2)

    out = adv.mutate(caught, _score_two_axis(caught))

    assert out is not None
    assert getattr(out, "amt") == 50.0
    assert getattr(out, "merchant_risk") == 0.1
    assert _is_fraud_night(out) is True            # intent preserved
    assert _score_two_axis(out) < 0.5              # victim clears
    # The catalog records BOTH moved features (a real multi-feature tactic).
    summary = catalog.summary()
    moved = {(row["feature"], row["direction"]) for row in summary}
    assert ("amt", "decrease") in moved
    assert ("merchant_risk", "decrease") in moved


def test_budget_zero_returns_none_without_calling_provider() -> None:
    class _Boom:
        def complete(self, *a: object, **k: object) -> object:
            raise AssertionError("provider must not be called when budget is 0")

    adv = LlmRedAdversary(
        provider=_Boom(),  # type: ignore[arg-type]
        spec=_SPEC,
        score_fn=_score_high_amt,
        label_fn=_is_fraud_night,
        threshold=0.5,
        max_calls=0,
    )
    caught = _Txn(txn_index=0, amt=1500.0, merchant_risk=0.9, hour=2)

    assert adv.mutate(caught, _score_high_amt(caught)) is None
    assert adv.calls_made == 0


def test_invalid_feature_proposal_is_rejected() -> None:
    # LLM proposes a non-existent field -> rejected; with max_attempts=1 -> None.
    adv = LlmRedAdversary(
        provider=MockProvider(
            text='{"moves":[{"feature":"nope","new_value":1.0}],"rationale":"x"}'
        ),
        spec=_SPEC,
        score_fn=_score_high_amt,
        label_fn=_is_fraud_night,
        threshold=0.5,
        max_attempts=1,
    )
    caught = _Txn(txn_index=0, amt=1500.0, merchant_risk=0.9, hour=2)
    assert adv.mutate(caught, _score_high_amt(caught)) is None


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="no ANTHROPIC_API_KEY",
)
def test_live_one_real_sonnet_call() -> None:
    """ONE real Sonnet 4.6 call on a real Sparkov caught-fraud sample."""
    from examples.targets import fraud_sparkov

    spec = fraud_sparkov.load_spec()
    threshold = fraud_sparkov.DETECTOR_THRESHOLD
    from modules.targets.local_model.adapter import LocalModelTarget

    detector = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    # A real night-hour, high-amount caught fraud.
    batch = fraud_sparkov.generate_batch("llm-red-live", 200)
    caught = next(
        t
        for t in batch
        if fraud_sparkov.is_fraud(t) and detector.score(t) >= threshold
    )
    adv = LlmRedAdversary(
        provider=AnthropicApiProvider(model="claude-sonnet-4-6"),
        spec=spec,
        score_fn=detector.score,
        label_fn=fraud_sparkov.is_fraud,
        threshold=threshold,
        max_attempts=1,
        max_calls=1,
    )
    out = adv.mutate(caught, detector.score(caught))
    assert out is None or fraud_sparkov.is_fraud(out)
    assert adv.calls_made <= 1
