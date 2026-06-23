import hashlib
import random
from shared.types import Transaction
from examples.targets.fraud_synth.constants import BATCH_FRAUD_RATE


def _rng(seed: str) -> random.Random:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return random.Random(int(h, 16))


def _draw(rng: random.Random, idx: int, force_fraud: bool) -> Transaction:
    # Bias features so roughly BATCH_FRAUD_RATE of draws satisfy the rule;
    # force_fraud nudges a draw into the fraud region deterministically.
    if force_fraud:
        velocity = rng.randint(6, 15)
        country_mismatch = rng.random() < 0.5
        amount = rng.uniform(50.0, 1500.0)
        merchant_risk = rng.uniform(0.5, 1.0)
    else:
        velocity = rng.randint(0, 4)
        country_mismatch = False
        amount = rng.uniform(5.0, 700.0)
        merchant_risk = rng.uniform(0.0, 0.6)
    return Transaction(idx, round(amount, 2), velocity, country_mismatch,
                       round(merchant_risk, 3), rng.randint(0, 23))


def generate_batch(seed: str, size: int) -> list[Transaction]:
    rng = _rng(seed)
    n_fraud = int(size * BATCH_FRAUD_RATE)
    flags = [True] * n_fraud + [False] * (size - n_fraud)
    rng.shuffle(flags)
    batch = [_draw(rng, i, flags[i]) for i in range(size)]
    # The rule is authoritative; `flags` only biases sampling.
    return batch
