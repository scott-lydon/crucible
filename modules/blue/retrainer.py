"""Blue retrainer — turns a feature set into a hardened detector.

Generic over the victim: the actual training lives in the victim example and is
INJECTED as ``retrain_fn``. The retrainer calls it with the chosen feature set
and returns the resulting detector (anything exposing ``.score(sample) -> float``,
i.e. the Target ``Detector`` protocol). The harness never knows HOW the victim
retrains — it only knows the feature set to ask for and the Detector it gets back.
"""

from collections.abc import Callable, Sequence

from orchestrator.interfaces import Detector


class BlueRetrainer:
    """Retrains the victim detector over a feature set via an injected callback."""

    def __init__(self, retrain_fn: Callable[[Sequence[str]], Detector]) -> None:
        self._retrain_fn = retrain_fn

    def retrain(self, feature_set: Sequence[str]) -> Detector:
        """Retrain over ``feature_set`` and return the new detector.

        Fails loud if the injected callback returns something that cannot score.
        """
        if not feature_set:
            raise ValueError("BlueRetrainer: feature_set must be non-empty.")
        detector = self._retrain_fn(list(feature_set))
        if not hasattr(detector, "score") or not callable(detector.score):
            raise TypeError(
                "BlueRetrainer: retrain_fn must return a Detector with a callable "
                f"`.score`; got {type(detector).__name__}."
            )
        return detector
