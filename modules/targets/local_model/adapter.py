"""Generic adapter that loads a serialized model from disk and scores samples.

This is HARNESS code: a dataset-agnostic seam implementing the Target Protocol
(`orchestrator.interfaces.target.Detector`). It reads spec/config-named features
off any sample and feeds them to a serialized scikit-learn-style estimator.

No victim-specific knowledge lives here — the adapter is fully generic over the
caller-supplied ``feature_names``. Victims live in ``examples/``; this package
imports ONLY from ``shared/`` and ``orchestrator/interfaces/`` (in practice it
needs neither at runtime — it depends only on the structural Detector contract).
"""

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import joblib

_DATA_DIR_ENV = "CRUCIBLE_DATA_DIR"
_DEFAULT_DATA_DIR = "./data"


@runtime_checkable
class _Estimator(Protocol):
    """Structural type for the serialized model. Either a probabilistic
    classifier (``predict_proba``) or a plain predictor (``predict``)."""

    def predict(self, X: Sequence[Sequence[float]]) -> Sequence[Any]: ...


def resolve_data_path(model_path: str | Path) -> Path:
    """Resolve ``model_path`` against ``CRUCIBLE_DATA_DIR`` when it is relative.

    Absolute paths are returned untouched. Relative paths are joined onto the
    data dir from the env var (default ``./data``), so model artifacts stay
    external and relocatable.
    """
    path = Path(model_path)
    if path.is_absolute():
        return path
    data_dir = Path(os.environ.get(_DATA_DIR_ENV, _DEFAULT_DATA_DIR))
    return data_dir / path


class LocalModelTarget:
    """Loads a serialized model lazily and scores arbitrary samples.

    The model is NOT loaded in ``__init__`` so the adapter can be constructed
    before the artifact exists (e.g. wiring time). It loads on first ``score``
    and is cached thereafter; a missing artifact fails loud at first use.
    """

    def __init__(self, model_path: str | Path, feature_names: Sequence[str]) -> None:
        self._model_path: Path = resolve_data_path(model_path)
        self._feature_names: tuple[str, ...] = tuple(feature_names)
        self._model: _Estimator | None = None

    def _load_model(self) -> _Estimator:
        if self._model is not None:
            return self._model
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"LocalModelTarget: model artifact not found at '{self._model_path}'. "
                f"Model artifacts are external inputs resolved relative to "
                f"${_DATA_DIR_ENV} (default '{_DEFAULT_DATA_DIR}'); ensure the file "
                f"exists or set {_DATA_DIR_ENV} to point at it. No fallback model is used."
            )
        model: _Estimator = joblib.load(self._model_path)
        self._model = model
        return model

    def _build_vector(self, sample: object) -> list[float]:
        vec: list[float] = []
        for name in self._feature_names:
            try:
                raw = getattr(sample, name)
            except AttributeError as exc:
                raise ValueError(
                    f"LocalModelTarget: sample is missing required feature '{name}' "
                    f"(expected features: {list(self._feature_names)}). "
                    f"Refusing to default a missing feature to 0."
                ) from exc
            # Coerce bool->float explicitly (bool is a subclass of int), leave
            # numerics as float. No silent string coercion.
            vec.append(float(raw))
        return vec

    def score(self, sample: object) -> float:
        vec = self._build_vector(sample)
        model = self._load_model()

        proba = getattr(model, "predict_proba", None)
        if callable(proba):
            row = proba([vec])[0]
            # Positive/fraud class is index 1 for binary classifiers; guard for
            # degenerate single-class estimators.
            idx = 1 if len(row) > 1 else 0
            return float(row[idx])

        return float(model.predict([vec])[0])
