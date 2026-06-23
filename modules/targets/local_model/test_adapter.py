from dataclasses import dataclass
from pathlib import Path

import joblib
import pytest
from sklearn.linear_model import LogisticRegression

from modules.targets.local_model.adapter import LocalModelTarget


@dataclass(frozen=True)
class _Sample:
    a: float
    b: float


@dataclass(frozen=True)
class _PartialSample:
    a: float  # deliberately missing "b"


def _train_tiny_model(path: Path) -> None:
    # TEST FIXTURE ONLY: a trivial 2-feature dataset to exercise load+predict.
    # This is not product data — it just makes a real serialized estimator.
    features = [[0.0, 0.0], [0.1, 0.0], [0.0, 0.1], [1.0, 1.0], [0.9, 1.0], [1.0, 0.9]]
    labels = [0, 0, 0, 1, 1, 1]
    model = LogisticRegression()
    model.fit(features, labels)
    joblib.dump(model, path)


def test_scores_via_loaded_model(tmp_path: Path) -> None:
    model_file = tmp_path / "tiny_model.pkl"
    _train_tiny_model(model_file)

    target = LocalModelTarget(model_path=model_file, feature_names=["a", "b"])
    sample = _Sample(a=1.0, b=1.0)

    first = target.score(sample)
    second = target.score(sample)

    assert 0.0 <= first <= 1.0
    assert first == second  # deterministic, model cached after first load


def test_missing_model_fails_loud(tmp_path: Path) -> None:
    target = LocalModelTarget("/nonexistent/model.pkl", ["a"])
    sample = _Sample(a=1.0, b=2.0)

    with pytest.raises(FileNotFoundError) as exc:
        target.score(sample)

    assert "/nonexistent/model.pkl" in str(exc.value)


def test_missing_feature_fails_loud(tmp_path: Path) -> None:
    model_file = tmp_path / "tiny_model.pkl"
    _train_tiny_model(model_file)

    target = LocalModelTarget(model_path=model_file, feature_names=["a", "b"])
    sample = _PartialSample(a=1.0)

    with pytest.raises(ValueError) as exc:
        target.score(sample)

    assert "b" in str(exc.value)
