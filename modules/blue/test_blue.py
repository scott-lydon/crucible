"""Unit tests for the blue pillar — proposer, retrainer, validator.

All offline/deterministic: MockProvider or budget-0 for the proposer, a stub
retrain_fn for the retrainer, an in-process scoring detector for the validator.
No real LLM calls, no real data.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from modules.blue.proposer import BlueProposer, ProposedPatch
from modules.blue.retrainer import BlueRetrainer
from modules.blue.validator import HoldoutValidator
from shared.llm import MockProvider

_CATALOG = [
    {"feature": "amt", "direction": "decrease", "source": "llm", "count": 7},
]
_CURRENT = ["amt", "cat_risk"]
_AVAILABLE = ["amt", "cat_risk", "hour", "distance"]


# --- proposer --------------------------------------------------------------


def test_proposer_parses_mock_features() -> None:
    provider = MockProvider(
        text='{"features_to_add": ["hour", "distance"], "rationale": "close the gap"}'
    )
    proposer = BlueProposer(provider, max_calls=5)
    patch = proposer.propose(_CATALOG, _CURRENT, _AVAILABLE)
    assert patch.features_to_add == ["hour", "distance"]
    assert patch.rationale == "close the gap"
    assert proposer.calls_made == 1


def test_proposer_drops_already_used_and_bogus_features() -> None:
    # "amt" is already current; "bogus" is not on the menu — both dropped.
    provider = MockProvider(
        text='{"features_to_add": ["amt", "hour", "bogus"], "rationale": "x"}'
    )
    proposer = BlueProposer(provider, max_calls=5)
    patch = proposer.propose(_CATALOG, _CURRENT, _AVAILABLE)
    assert patch.features_to_add == ["hour"]


def test_proposer_budget_zero_uses_deterministic_fallback() -> None:
    # Budget 0 -> never touches the provider -> proposes every unused feature.
    provider = MockProvider(text="should-not-be-used")
    proposer = BlueProposer(provider, max_calls=0)
    patch = proposer.propose(_CATALOG, _CURRENT, _AVAILABLE)
    assert patch.features_to_add == ["hour", "distance"]
    assert proposer.calls_made == 0
    assert "fallback" in patch.rationale.lower()


def test_proposer_empty_proposal_falls_back() -> None:
    provider = MockProvider(text='{"features_to_add": [], "rationale": "nothing"}')
    proposer = BlueProposer(provider, max_calls=5)
    patch = proposer.propose(_CATALOG, _CURRENT, _AVAILABLE)
    assert patch.features_to_add == ["hour", "distance"]


# --- retrainer -------------------------------------------------------------


@dataclass
class _StubDetector:
    features: tuple[str, ...]

    def score(self, sample: object) -> float:
        return 1.0


def test_retrainer_returns_injected_detector() -> None:
    seen: dict[str, object] = {}

    def fake_retrain(feature_set: Sequence[str]) -> _StubDetector:
        seen["features"] = list(feature_set)
        return _StubDetector(features=tuple(feature_set))

    retrainer = BlueRetrainer(retrain_fn=fake_retrain)
    detector = retrainer.retrain(["amt", "hour"])
    assert isinstance(detector, _StubDetector)
    assert detector.features == ("amt", "hour")
    assert seen["features"] == ["amt", "hour"]


# --- validator -------------------------------------------------------------


@dataclass(frozen=True)
class _Sample:
    txn_index: int
    amt: float
    hour: int


class _NightCatchingDetector:
    """Catches night-hour samples regardless of amount."""

    def score(self, sample: object) -> float:
        return 0.9 if getattr(sample, "hour") in (0, 1, 2) else 0.1


class _AmtOnlyDetector:
    """Clears low-amount samples (the old, blind detector)."""

    def score(self, sample: object) -> float:
        return 0.9 if getattr(sample, "amt") > 100 else 0.1


def _is_night_fraud(sample: object) -> bool:
    return getattr(sample, "hour") in (0, 1, 2)


def test_validator_computes_recovery() -> None:
    # Holdout: night frauds with amt lowered to evade an amt-only detector.
    holdout = [_Sample(txn_index=i, amt=10.0, hour=1) for i in range(5)]
    result = HoldoutValidator().validate(
        new_detector=_NightCatchingDetector(),
        holdout_samples=holdout,
        label_fn=_is_night_fraud,
        threshold=0.5,
        old_detector=_AmtOnlyDetector(),
    )
    assert result.n == 5
    assert result.detection_before == 0.0  # old detector clears all (low amt)
    assert result.detection_after == 1.0  # new detector catches all (night)
    assert result.recovered == 1.0


def test_validator_ignores_label_flipped_samples() -> None:
    # A daytime sample is NOT fraud per label_fn -> excluded from n entirely.
    holdout = [_Sample(0, 10.0, 1), _Sample(1, 10.0, 12)]
    result = HoldoutValidator().validate(
        new_detector=_NightCatchingDetector(),
        holdout_samples=holdout,
        label_fn=_is_night_fraud,
        threshold=0.5,
    )
    assert result.n == 1  # only the night sample counts
    assert result.detection_after == 1.0


def test_validator_empty_holdout() -> None:
    result = HoldoutValidator().validate(
        new_detector=_NightCatchingDetector(),
        holdout_samples=[],
        label_fn=_is_night_fraud,
        threshold=0.5,
    )
    assert result == result.__class__(0.0, 0.0, 0.0, 0)


def test_proposed_patch_defaults() -> None:
    patch = ProposedPatch()
    assert patch.features_to_add == []
    assert patch.rationale == ""
