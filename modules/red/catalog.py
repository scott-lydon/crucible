"""In-memory catalog of successful evasion strategies.

The red loop records every landed evasion here — which feature it moved, in
which direction, and whether the move came from the LLM red agent or the
deterministic fallback. The blue pillar will read ``summary()`` to learn what
the adversary is exploiting and propose detector hardening. No persistence is
needed yet: the loop already persists the attacks themselves; this is a
lightweight running aggregate the proposer can consult in-process.
"""

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _Key:
    feature: str
    direction: str
    source: str


class StrategyCatalog:
    """Counts successful evasion strategies by (feature, direction, source)."""

    def __init__(self) -> None:
        self._counts: Counter[_Key] = Counter()

    def record(self, feature: str, direction: str, source: str) -> None:
        """Record one landed evasion. ``source`` is "llm" or "deterministic"."""
        self._counts[_Key(feature=feature, direction=direction, source=source)] += 1

    def summary(self) -> list[dict[str, object]]:
        """Per-strategy counts, sorted most-used first then by key for stability."""
        return [
            {
                "feature": key.feature,
                "direction": key.direction,
                "source": key.source,
                "count": count,
            }
            for key, count in sorted(
                self._counts.items(),
                key=lambda item: (-item[1], item[0].feature, item[0].direction, item[0].source),
            )
        ]
