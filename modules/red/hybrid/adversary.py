"""Hybrid adversary: LLM-first, deterministic-fallback (slice-13).

Tries the ``primary`` adversary (the real LLM red agent); if it returns ``None``
— no evasion found, or its cost budget is exhausted — delegates to the
``fallback`` adversary (the free deterministic mutator). This is the wired
adversary for the demo: it gets the LLM's creativity when the budget allows and
ALWAYS keeps functioning afterwards, which also bounds spend (once the LLM
budget runs out, the free deterministic path drives the loop).
"""

from orchestrator.interfaces import Adversary


class HybridAdversary:
    """Adversary that prefers ``primary`` and falls back to ``fallback``."""

    def __init__(self, primary: Adversary, fallback: Adversary) -> None:
        self._primary = primary
        self._fallback = fallback

    def mutate(self, sample: object, score: float) -> object | None:
        result = self._primary.mutate(sample, score)
        if result is not None:
            return result
        return self._fallback.mutate(sample, score)
