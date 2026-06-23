"""Smoke tests for orchestrator.wiring.build_components and orchestrator.db."""
from orchestrator.wiring import build_components


def test_build_components_keys() -> None:
    comp = build_components(threshold=0.5)
    assert set(comp.keys()) == {"detector", "adversary", "oracles", "label_fn", "generate_fn"}


def test_oracles_list_length() -> None:
    comp = build_components(threshold=0.5)
    oracles = comp["oracles"]
    assert isinstance(oracles, list)
    assert len(oracles) == 5


def test_label_fn_callable() -> None:
    comp = build_components(threshold=0.5)
    assert callable(comp["label_fn"])


def test_generate_fn_callable() -> None:
    comp = build_components(threshold=0.5)
    assert callable(comp["generate_fn"])
