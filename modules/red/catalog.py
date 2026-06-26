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


@dataclass(frozen=True, slots=True)
class VectorProvenance:
    """One LLM-chosen attack VECTOR and how its values were landed.

    Records that the LLM owned the STRATEGY (which features, which directions, and
    why) while a deterministic solver refined the concrete numbers — so a reader
    can see the model drove the attack and the solver only landed it (no script
    masquerading as the model). ``directions`` maps each chosen feature to the
    direction the LLM picked ("increase"/"decrease"); ``rationale`` is the LLM's
    own one-line reasoning; ``solved`` is True when a numeric search found the
    landing values.
    """

    directions: tuple[tuple[str, str], ...]
    rationale: str
    solved: bool


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
        self._vectors: list[VectorProvenance] = []

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

    def record_vector(
        self,
        directions: dict[str, str],
        rationale: str,
        *,
        solved: bool,
    ) -> None:
        """Record one LLM-chosen attack VECTOR + how it was landed (provenance).

        Keeps the LLM's strategy (chosen features + directions + rationale)
        DISTINCT from the blind per-feature counts of :meth:`record`, so the
        provenance shows the model drove the attack and the deterministic solver
        only refined the value. ``solved`` is True when the numeric search landed
        the vector. Also records each moved feature in the per-feature view (with
        source ``"discover_solve"``) so the blue pillar's existing reader still
        sees what was exploited.
        """
        self._vectors.append(
            VectorProvenance(
                directions=tuple(sorted(directions.items())),
                rationale=rationale,
                solved=solved,
            )
        )
        if solved:
            for feature_name, direction in directions.items():
                self.record(
                    feature=feature_name,
                    direction=direction,
                    source="discover_solve",
                )

    def vector_provenance(self) -> list[VectorProvenance]:
        """The LLM-chosen vectors recorded, in the order they landed."""
        return list(self._vectors)

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
