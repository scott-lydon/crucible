from shared.types import Transaction
from modules.red.mutator.mutator import AmountLoweringAdversary
from modules.targets.fraud_detector.detector import FlawedDetector
from modules.targets.synth.rule import is_fraud
from modules.targets.synth.constants import DETECTOR_THRESHOLD


def _adv() -> AmountLoweringAdversary:
    d = FlawedDetector()
    return AmountLoweringAdversary(score_fn=d.score, label_fn=is_fraud,
                                   threshold=DETECTOR_THRESHOLD)


def test_mutation_evades_and_preserves_fraud() -> None:
    # caught high-amount fraud that is ALSO fraud by velocity
    caught = Transaction(0, amount=1500.0, velocity=12, country_mismatch=True,
                         merchant_risk=0.9, hour_of_day=2)
    adv = _adv()
    out = adv.mutate(caught, FlawedDetector().score(caught))
    assert out is not None
    assert out.velocity == caught.velocity and out.country_mismatch  # signals preserved
    assert is_fraud(out) is True                                     # still real fraud
    assert FlawedDetector().score(out) < DETECTOR_THRESHOLD          # now evades


def test_returns_none_when_fraud_only_by_amount() -> None:
    # fraud caused ONLY by amount+risk: lowering amount would flip the label -> reject
    amount_only = Transaction(1, amount=1500.0, velocity=0, country_mismatch=False,
                              merchant_risk=0.9, hour_of_day=2)
    adv = _adv()
    assert adv.mutate(amount_only, FlawedDetector().score(amount_only)) is None
