"""Property-fuzz oracle (slice-8): generative search for invariant counterexamples.

Where the InvariantOracle CHECKS one observed sample against a `must_flag_when`
invariant, this oracle GENERATIVELY SEARCHES for an input that satisfies a
declared invariant yet the detector clears — the generative superset of the
invariant check. It is a pure-Hypothesis probe: NO LLM call, seeded so it is
deterministic, and target-agnostic (the victim injects both the detector query
(`score_fn`) and a Hypothesis strategy that generates victim sample objects, so
the oracle hardcodes no feature names).

The property under test, derived from `ctx.spec.invariants` (kind
`must_flag_when`):

    ∀ generated sample s: if s satisfies the invariant's condition C,
    then score_fn(s) >= threshold   (the detector MUST flag it).

A counterexample is a generated sample where C holds but the detector cleared it
(score < threshold) — proof the detector clears an input a declared invariant
says must be flagged. Hypothesis SHRINKS to a minimal counterexample.

RUN-LEVEL PROBE: the property is a property of the detector + spec, not of
`ctx.sample`. The full bounded search runs ONCE and the result is memoized on the
instance, so the SAME verdict surfaces (cheaply) on each per-sample card without
re-searching. One PropertyFuzzOracle instance is wired per run.
"""

import dataclasses
import random
from collections.abc import Callable, Mapping
from typing import cast

from hypothesis import HealthCheck, find, settings
from hypothesis.errors import NoSuchExample
from hypothesis.strategies import SearchStrategy

from shared.types import OracleKind, OracleVote, VerdictContext, Vote
from shared.types.invariant_eval import all_conditions_hold


@dataclasses.dataclass(frozen=True, slots=True)
class _Result:
    """Memoized outcome of the run-level search (None counterexample => PASS)."""

    counterexample: object | None
    invariant_id: str | None
    score: float | None
    examples_tried: int


def _as_evidence(sample: object) -> object:
    """Best-effort JSON-friendly view of a generated sample for the card."""
    if dataclasses.is_dataclass(sample) and not isinstance(sample, type):
        return dataclasses.asdict(sample)
    return repr(sample)


class PropertyFuzzOracle:
    """Hypothesis-based generative search for `must_flag_when` counterexamples."""

    def __init__(
        self,
        score_fn: Callable[[object], float],
        strategy: SearchStrategy,
        *,
        max_examples: int = 100,
        seed: int = 0,
    ) -> None:
        self._score_fn = score_fn
        self._strategy = strategy
        self._max_examples = max_examples
        self._seed = seed
        # Run-level memo: keyed by the spec object identity so a reused instance
        # across specs stays correct, but in practice one instance == one run.
        self._cached: _Result | None = None
        self._cached_spec_id: int | None = None

    @property
    def kind(self) -> OracleKind:
        return OracleKind.PROPERTY_FUZZ

    def vote(self, ctx: VerdictContext) -> OracleVote:
        result = self._search(ctx)
        if result.counterexample is not None:
            return OracleVote(
                kind=self.kind,
                vote=Vote.FAIL,
                weight=1.0,
                reason=(
                    f"generated input satisfies invariant '{result.invariant_id}' "
                    f"but the detector cleared it (score {result.score} < "
                    f"{ctx.threshold})"
                ),
                evidence={
                    "counterexample": _as_evidence(result.counterexample),
                    "invariant_id": result.invariant_id,
                    "score": result.score,
                    "threshold": ctx.threshold,
                    "examples_tried": result.examples_tried,
                    "run_level": True,
                },
            )
        return OracleVote(
            kind=self.kind,
            vote=Vote.PASS,
            weight=1.0,
            reason=(
                f"no counterexample found in {result.examples_tried} examples: "
                "every generated input satisfying a must-flag invariant was flagged"
            ),
            evidence={"examples_tried": result.examples_tried, "run_level": True},
        )

    # --- run-level search (memoized) -------------------------------------

    def _search(self, ctx: VerdictContext) -> _Result:
        spec_id = id(ctx.spec)
        if self._cached is not None and self._cached_spec_id == spec_id:
            return self._cached

        must_flag = [
            inv for inv in ctx.spec.invariants if inv.kind == "must_flag_when"
        ]
        threshold = ctx.threshold
        # We track how many examples Hypothesis tried (bounds the cost claim) and
        # which invariant a found counterexample violated.
        tried = {"n": 0}
        hit: dict[str, object] = {}

        def violates(sample: object) -> bool:
            tried["n"] += 1
            for inv in must_flag:
                all_of = cast(
                    list[Mapping[str, object]], inv.params.get("all_of", [])
                )
                if not all_conditions_hold(sample, all_of):
                    continue
                score = self._score_fn(sample)
                if score < threshold:
                    # A generated input satisfies the invariant yet was cleared.
                    hit["invariant_id"] = inv.name
                    hit["score"] = float(score)
                    return True
            return False

        # Seeded + derandomized => same seed yields the same shrunk counterexample.
        # An explicit seeded Random is the deterministic seam (`find` accepts it);
        # derandomize=True + database=None keep runs reproducible and stateless.
        # suppress_health_check: the predicate may reject many draws before a
        # match; that filtering is intended, not a sign of a slow strategy.
        run_settings = settings(
            max_examples=self._max_examples,
            derandomize=True,
            database=None,
            deadline=None,
            suppress_health_check=list(HealthCheck),
        )

        try:
            minimal: object | None = find(
                self._strategy,
                violates,
                settings=run_settings,
                random=random.Random(self._seed),
            )
        except NoSuchExample:
            minimal = None

        if minimal is None:
            result = _Result(
                counterexample=None,
                invariant_id=None,
                score=None,
                examples_tried=tried["n"],
            )
        else:
            # Re-evaluate the minimal example to capture its invariant id + score
            # (the predicate ran many times during shrinking; recompute cleanly).
            violates(minimal)
            result = _Result(
                counterexample=minimal,
                invariant_id=cast(str, hit.get("invariant_id")),
                score=cast(float, hit.get("score")),
                examples_tried=tried["n"],
            )

        self._cached = result
        self._cached_spec_id = spec_id
        return result
