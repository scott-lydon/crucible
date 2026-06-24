"""Unit tests for DummyTarget. No database, no network."""

from __future__ import annotations

from modules.targets.dummy import DummyTarget
from shared.types import ProbeStatus, SealedSpec, TargetType


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {"title": "t", "obligations": [{"id": "o1", "description": "d"}]}
    )


def test_dummy_target_type_is_dummy() -> None:
    assert DummyTarget().target_type == TargetType.DUMMY


async def test_submit_echoes_input_and_checks_first_obligation() -> None:
    out = await DummyTarget().submit(_spec(), {"x": 1})
    assert out.output["echo"] == {"x": 1}
    assert out.output["checked_obligation"] == "o1"
    assert out.score is not None
    assert 0.0 <= out.score <= 1.0


async def test_query_target_is_deterministic() -> None:
    target = DummyTarget()
    first = await target.query_target({"x": 1})
    second = await target.query_target({"x": 1})
    assert first == second


async def test_self_test_is_green() -> None:
    result = await DummyTarget().self_test()
    assert result.status == ProbeStatus.GREEN
