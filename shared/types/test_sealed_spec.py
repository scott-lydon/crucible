import dataclasses
from pathlib import Path

import pytest

from shared.types import (
    Invariant,
    MetamorphicRelation,
    SealedSpec,
    sealed_spec_from_dict,
    sealed_spec_from_yaml,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FRAUD_SPEC_PATH = REPO_ROOT / "specs" / "fraud_v0.yaml"


def _valid_dict() -> dict[str, object]:
    return {
        "target_kind": "fraud",
        "obligations": ["flag truly fraudulent", "no amount-only evasion"],
        "invariants": [
            {
                "name": "country_velocity_must_flag",
                "description": "country_mismatch + high velocity must flag",
                "kind": "must_flag_when",
                "params": {
                    "all_of": [
                        {"feature": "country_mismatch", "eq": True},
                        {"feature": "velocity", "gt": 5},
                    ]
                },
            }
        ],
        "metamorphic_relations": [
            {
                "name": "amount_decrease_label_invariance",
                "description": "lowering amount must not change label",
                "feature": "amount",
                "direction": "decrease",
                "label_must_change": False,
            }
        ],
        "holdout_generator_kind": "deterministic_rule",
    }


def test_from_dict_builds_typed_object() -> None:
    spec = sealed_spec_from_dict(_valid_dict())
    assert spec.target_kind == "fraud"

    assert isinstance(spec.invariants, tuple)
    assert all(isinstance(inv, Invariant) for inv in spec.invariants)

    assert isinstance(spec.metamorphic_relations, tuple)
    assert all(isinstance(mr, MetamorphicRelation) for mr in spec.metamorphic_relations)

    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.target_kind = "other"  # type: ignore[misc]


def test_from_dict_rejects_missing_required() -> None:
    data = _valid_dict()
    del data["holdout_generator_kind"]
    with pytest.raises(ValueError):
        sealed_spec_from_dict(data)


def test_from_dict_rejects_wrong_type() -> None:
    data = _valid_dict()
    data["obligations"] = "not a list"
    with pytest.raises(ValueError):
        sealed_spec_from_dict(data)


def test_from_yaml_loads_fraud_spec() -> None:
    text = FRAUD_SPEC_PATH.read_text()
    spec = sealed_spec_from_yaml(text)

    assert spec.target_kind == "fraud"

    names = {inv.name for inv in spec.invariants}
    assert "country_velocity_must_flag" in names

    relation = next(
        mr for mr in spec.metamorphic_relations if mr.name == "amount_decrease_label_invariance"
    )
    assert relation.feature == "amount"
    assert relation.direction == "decrease"
    assert relation.label_must_change is False


def test_isinstance_sealed_spec() -> None:
    spec = sealed_spec_from_yaml(FRAUD_SPEC_PATH.read_text())
    assert isinstance(spec, SealedSpec)
