"""Blue round orchestration — propose -> retrain -> validate.

Ties the three blue stages into one honest co-evolution recovery step:

1. The proposer reads the red loop's evasion catalog and the current vs available
   feature sets, and proposes which unused features to add.
2. The retrainer rebuilds the victim detector over ``current + added`` features
   (via the injected victim ``retrain_fn``).
3. The validator measures detection on the held-out evasions before vs after.

Returns a ``BlueResult`` carrying the patch, the new detector, the new model
path (when the retrain surfaced one), and the before/after/recovered numbers.
Persistence is optional and best-effort (a minimal ``BlueRoundRow``); the demo
never blocks on schema work.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from orchestrator.interfaces import Detector
from modules.blue.proposer import BlueProposer, ProposedPatch
from modules.blue.retrainer import BlueRetrainer
from modules.blue.validator import HoldoutValidator, ValidationResult


@dataclass(frozen=True, slots=True)
class BlueResult:
    """The outcome of one blue round."""

    patch: ProposedPatch
    new_features: list[str]
    new_detector: Detector
    new_model_path: Path | None
    validation: ValidationResult


def run_blue_round(
    *,
    catalog: object,
    current_features: Sequence[str],
    available_features: Sequence[str],
    retrain_fn: Callable[[Sequence[str]], object],
    holdout_samples: Sequence[object],
    label_fn: Callable[[object], bool],
    threshold: float,
    proposer: BlueProposer,
    old_detector: Detector | None = None,
    validator: HoldoutValidator | None = None,
) -> BlueResult:
    """Run one propose -> retrain -> validate blue round and return the result."""
    catalog_summary = _catalog_summary(catalog)
    patch = proposer.propose(catalog_summary, current_features, available_features)

    # Retrain on the union, current first, preserving order and de-duplicating.
    new_features: list[str] = list(current_features)
    for feat in patch.features_to_add:
        if feat not in new_features:
            new_features.append(feat)

    retrainer = BlueRetrainer(retrain_fn=_as_detector_fn(retrain_fn))
    new_detector = retrainer.retrain(new_features)

    validator = validator if validator is not None else HoldoutValidator()
    validation = validator.validate(
        new_detector,
        holdout_samples,
        label_fn,
        threshold,
        old_detector=old_detector,
    )

    return BlueResult(
        patch=patch,
        new_features=new_features,
        new_detector=new_detector,
        new_model_path=getattr(new_detector, "model_path", None),
        validation=validation,
    )


def _catalog_summary(catalog: object) -> list[dict[str, object]]:
    """Read a catalog's ``summary()`` if present; tolerate a plain list/None."""
    if catalog is None:
        return []
    summary = getattr(catalog, "summary", None)
    if callable(summary):
        return list(summary())
    if isinstance(catalog, list):
        return catalog
    return []


def _as_detector_fn(
    retrain_fn: Callable[[Sequence[str]], object],
) -> Callable[[Sequence[str]], Detector]:
    """Adapt the loosely-typed injected retrain_fn to the retrainer's contract."""

    def _call(feature_set: Sequence[str]) -> Detector:
        result = retrain_fn(feature_set)
        return result  # type: ignore[return-value]

    return _call
