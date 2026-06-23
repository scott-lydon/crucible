import dataclasses
import pytest
from shared.types import Transaction, OracleVote, OracleKind, Vote

def test_transaction_is_frozen_and_slotted() -> None:
    t = Transaction(txn_index=0, amount=10.0, velocity=1, country_mismatch=False,
                    merchant_risk=0.1, hour_of_day=9)
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.amount = 5.0  # type: ignore[misc]

def test_oracle_vote_round_trip() -> None:
    v = OracleVote(kind=OracleKind.INVARIANT, vote=Vote.FAIL, weight=1.0,
                   reason="rule violated", evidence={"rule": "country+velocity"})
    assert v.vote is Vote.FAIL and v.weight == 1.0
