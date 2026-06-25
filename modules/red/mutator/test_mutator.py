import pathlib
from dataclasses import dataclass

from shared.types import sealed_spec_from_yaml
from modules.red.mutator.mutator import MetamorphicEvasionAdversary
from examples.targets.fraud_synth import (
    DETECTOR_THRESHOLD,
    FlawedDetector,
    Transaction,
    is_fraud,
)

_SPEC = sealed_spec_from_yaml(
    (pathlib.Path(__file__).resolve().parents[3] / "specs" / "fraud_v0.yaml").read_text()
)


def _adv() -> MetamorphicEvasionAdversary:
    d = FlawedDetector()
    return MetamorphicEvasionAdversary(score_fn=d.score, label_fn=is_fraud,
                                       threshold=DETECTOR_THRESHOLD, spec=_SPEC)


def test_mutation_evades_and_preserves_fraud() -> None:
    # caught high-amount fraud that is ALSO fraud by velocity
    caught = Transaction(0, amount=1500.0, velocity=12, country_mismatch=True,
                         merchant_risk=0.9, hour_of_day=2)
    adv = _adv()
    out = adv.mutate(caught, FlawedDetector().score(caught))
    assert out is not None
    assert isinstance(out, Transaction)
    assert out.velocity == caught.velocity and out.country_mismatch  # signals preserved
    assert is_fraud(out) is True                                     # still real fraud
    assert FlawedDetector().score(out) < DETECTOR_THRESHOLD          # now evades


def test_returns_none_when_fraud_only_by_amount() -> None:
    # fraud caused ONLY by amount+risk: lowering amount would flip the label -> reject
    amount_only = Transaction(1, amount=1500.0, velocity=0, country_mismatch=False,
                              merchant_risk=0.9, hour_of_day=2)
    adv = _adv()
    assert adv.mutate(amount_only, FlawedDetector().score(amount_only)) is None


# --- Free, multi-feature deterministic search (no single hard axis) ---------


@dataclass(frozen=True, slots=True)
class _Txn:
    txn_index: int
    amt: float
    merchant_risk: float
    blind: int  # a signal the victim ignores; carries the true fraud label


def _two_axis_score(sample: object) -> float:
    # The victim clears ONLY when BOTH amt and merchant_risk are lowered — a
    # single-feature ladder can never satisfy it.
    if getattr(sample, "amt") <= 100.0 and getattr(sample, "merchant_risk") <= 0.3:
        return 0.1
    return 0.9


def _blind_is_fraud(sample: object) -> bool:
    # Fraud lives on the blind signal, so lowering amt/merchant_risk preserves it.
    return bool(getattr(sample, "blind") == 1)


def test_deterministic_mutator_lands_multi_feature_evasion() -> None:
    # FREE multi-feature: given the victim's whole visible feature SET (no single
    # axis declared), the deterministic search combines amt + merchant_risk to
    # clear the victim while the blind-signal fraud label is preserved.
    adv = MetamorphicEvasionAdversary(
        score_fn=_two_axis_score,
        label_fn=_blind_is_fraud,
        threshold=0.5,
        spec=_SPEC,
        movable_features=["amt", "merchant_risk"],
    )
    caught = _Txn(txn_index=0, amt=1500.0, merchant_risk=0.9, blind=1)

    out = adv.mutate(caught, _two_axis_score(caught))

    assert out is not None
    assert getattr(out, "amt") < 1500.0
    assert getattr(out, "merchant_risk") < 0.9   # MORE than amt moved
    assert _blind_is_fraud(out) is True          # intent preserved
    assert _two_axis_score(out) < 0.5            # victim clears
