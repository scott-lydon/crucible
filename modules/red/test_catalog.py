"""Unit tests for the strategy catalog."""

from modules.red.catalog import StrategyCatalog


def test_records_and_counts_by_feature_direction_source() -> None:
    cat = StrategyCatalog()
    cat.record("amt", "decrease", "llm")
    cat.record("amt", "decrease", "llm")
    cat.record("amt", "decrease", "deterministic")

    summary = cat.summary()
    assert summary[0] == {
        "feature": "amt",
        "direction": "decrease",
        "source": "llm",
        "count": 2,
    }
    assert {
        "feature": "amt",
        "direction": "decrease",
        "source": "deterministic",
        "count": 1,
    } in summary


def test_empty_summary() -> None:
    assert StrategyCatalog().summary() == []
