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


@dataclass(frozen=True, slots=True)
class _TacticKey:
    tactic: str
    source: str


class StrategyCatalog:
    """Counts successful evasion strategies.

    Two complementary views are kept so one catalog serves both victim shapes:

    * The fraud path records ``(feature, direction, source)`` via :meth:`record`
      (which feature the adversary moved and in which direction).
    * The code-agent reward-hack path has no single moved feature — the red
      adversary manipulates the TASK (narrowing visible tests, reframing the
      spec). It records a free-form ``(tactic, source)`` via :meth:`record_tactic`
      (e.g. ``"narrowed visible tests -> producer hardcoded"``).

    Both views are surfaced by :meth:`summary` / :meth:`tactic_summary`.
    """

    def __init__(self) -> None:
        self._counts: Counter[_Key] = Counter()
        self._tactics: Counter[_TacticKey] = Counter()

    def record(self, feature: str, direction: str, source: str) -> None:
        """Record one landed evasion. ``source`` is "llm" or "deterministic"."""
        self._counts[_Key(feature=feature, direction=direction, source=source)] += 1

    def record_tactic(self, tactic: str, source: str) -> None:
        """Record one landed reward-hack TACTIC (task-space manipulation).

        ``tactic`` is a free-form human label for what the red agent did to the
        TASK to induce the silent reward-hack (e.g. "narrowed visible tests so
        the producer hardcoded them"). ``source`` is "llm" (the red LLM chose it)
        or "deterministic". Used by the code-agent red, where there is no single
        moved feature to key on.
        """
        self._tactics[_TacticKey(tactic=tactic, source=source)] += 1

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

    def tactic_summary(self) -> list[dict[str, object]]:
        """Per-tactic counts, sorted most-used first then by key for stability."""
        return [
            {"tactic": key.tactic, "source": key.source, "count": count}
            for key, count in sorted(
                self._tactics.items(),
                key=lambda item: (-item[1], item[0].tactic, item[0].source),
            )
        ]
