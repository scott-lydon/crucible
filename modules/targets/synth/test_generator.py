from modules.targets.synth.generator import generate_batch
from modules.targets.synth.rule import is_fraud


def test_generation_is_deterministic() -> None:
    a = generate_batch("seed-1", 200)
    b = generate_batch("seed-1", 200)
    assert a == b


def test_different_seeds_differ() -> None:
    assert generate_batch("seed-1", 200) != generate_batch("seed-2", 200)


def test_fraud_rate_in_expected_band() -> None:
    batch = generate_batch("seed-1", 200)
    rate = sum(is_fraud(t) for t in batch) / len(batch)
    assert 0.10 <= rate <= 0.35  # ~BATCH_FRAUD_RATE with sampling slack


def test_velocity_alone_is_fraud() -> None:
    from shared.types import Transaction
    t = Transaction(0, amount=10.0, velocity=99, country_mismatch=False,
                    merchant_risk=0.0, hour_of_day=3)
    assert is_fraud(t) is True
