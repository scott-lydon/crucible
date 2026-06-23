from shared.types import Transaction
from modules.targets.fraud_detector.detector import FlawedDetector
from modules.targets.synth.constants import DETECTOR_THRESHOLD


def test_catches_high_amount_fraud() -> None:
    d = FlawedDetector()
    big = Transaction(0, amount=1500.0, velocity=1, country_mismatch=False,
                      merchant_risk=0.9, hour_of_day=2)
    assert d.score(big) >= DETECTOR_THRESHOLD


def test_blind_to_low_amount_velocity_fraud() -> None:
    # truly fraudulent by velocity, but low amount -> detector is fooled
    d = FlawedDetector()
    sneaky = Transaction(1, amount=12.0, velocity=12, country_mismatch=True,
                         merchant_risk=0.2, hour_of_day=4)
    assert d.score(sneaky) < DETECTOR_THRESHOLD


def test_score_is_deterministic_and_bounded() -> None:
    d = FlawedDetector()
    t = Transaction(2, 500.0, 3, False, 0.5, 10)
    assert d.score(t) == d.score(t)
    assert 0.0 <= d.score(t) <= 1.0
