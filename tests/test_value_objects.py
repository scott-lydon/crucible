"""Unit tests for the shared value objects. No database, no network.

These pin the loud-validation contract: a bad construction raises a typed
DomainValidationError whose message names the rule, so the failure is
diagnosable from the message alone.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shared.types import (
    AttackBudget,
    DomainValidationError,
    Money,
    RunId,
    SealedSpec,
)


def test_run_id_new_is_nonempty_and_distinct() -> None:
    a = RunId.new()
    b = RunId.new()
    assert a.value and b.value
    assert a != b


def test_run_id_rejects_empty() -> None:
    with pytest.raises(DomainValidationError, match="RunId"):
        RunId("")


def test_money_rejects_negative() -> None:
    with pytest.raises(DomainValidationError, match="non-negative"):
        Money(Decimal("-1"))


def test_money_of_avoids_binary_float_noise() -> None:
    # 0.1 + 0.2 via float is 0.30000000000000004; via Money.of it is exact.
    total = Money.of(0.1) + Money.of(0.2)
    assert total.dollars == Decimal("0.3")


def test_attack_budget_rejects_nonpositive_attempts() -> None:
    with pytest.raises(DomainValidationError, match="max_attempts"):
        AttackBudget(max_attempts=0, max_dollars=Money.zero())


def test_sealed_spec_from_payload_parses_obligations_and_invariants() -> None:
    spec = SealedSpec.from_payload(
        {
            "title": "sum two integers",
            "obligations": [{"id": "o1", "description": "returns the sum"}],
            "invariants": [{"id": "i1", "description": "adding zero is a no-op"}],
        }
    )
    assert spec.title == "sum two integers"
    assert spec.obligations[0].id == "o1"
    assert spec.invariants[0].id == "i1"
    assert spec.holdout_generator_kind == "llm_post_submit"


def test_sealed_spec_from_payload_rejects_missing_obligations() -> None:
    with pytest.raises(DomainValidationError, match="obligations"):
        SealedSpec.from_payload({"title": "x", "obligations": []})


def test_sealed_spec_as_json_round_trips_shape() -> None:
    spec = SealedSpec.from_payload(
        {"title": "t", "obligations": [{"id": "o1", "description": "d"}]}
    )
    blob = spec.as_json()
    assert blob["title"] == "t"
    assert blob["obligations"] == [{"id": "o1", "description": "d"}]
