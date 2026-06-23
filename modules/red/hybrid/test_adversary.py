"""Unit tests for the hybrid LLM-first, deterministic-fallback adversary."""

from modules.red.hybrid.adversary import HybridAdversary


class _Const:
    """An Adversary stub that always returns a fixed value."""

    def __init__(self, value: object | None) -> None:
        self._value = value
        self.calls = 0

    def mutate(self, sample: object, score: float) -> object | None:
        self.calls += 1
        return self._value


def test_primary_result_used_when_not_none() -> None:
    primary = _Const("primary-result")
    fallback = _Const("fallback-result")
    hybrid = HybridAdversary(primary=primary, fallback=fallback)

    assert hybrid.mutate(object(), 0.9) == "primary-result"
    assert fallback.calls == 0  # fallback never consulted


def test_falls_back_when_primary_returns_none() -> None:
    primary = _Const(None)
    fallback = _Const("fallback-result")
    hybrid = HybridAdversary(primary=primary, fallback=fallback)

    assert hybrid.mutate(object(), 0.9) == "fallback-result"
    assert primary.calls == 1
    assert fallback.calls == 1


def test_returns_none_when_both_return_none() -> None:
    hybrid = HybridAdversary(primary=_Const(None), fallback=_Const(None))
    assert hybrid.mutate(object(), 0.9) is None
