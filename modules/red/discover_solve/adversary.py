"""DISCOVER -> STRATEGIZE -> SOLVE red: the LLM DRIVES, a solver LANDS.

This synthesizes two failures we proved live. Pure-LLM red is a great strategist
but a poor one-shot numeric solver (it landed only 1 evasion: it reasons about
WHICH features to move but guesses the magnitudes). The deterministic ladder is a
good solver but has no strategy (it landed 13-19 by brute-walking every feature,
but it cannot innovate or combine creatively, and it is hand-fed the attack
surface). The meta-attacker, which let the LLM write its own mutation code, failed
because it was BLIND to feature sensitivity — it guessed in the dark.

The synthesis here keeps each part on what it is good at:

1. **DISCOVER (probe).** This is where target-agnosticism lives. We introspect the
   sample's numeric fields (``dataclasses.asdict``) and, for each one, perturb it
   up and down a little and measure the target's score delta via ``score_fn`` —
   producing a SENSITIVITY MAP (which fields move the score, and which direction
   LOWERS it). This REPLACES a hand-fed ``movable_features`` list: the agent
   LEARNS the attack surface by querying the target. Generic for any queryable
   target whose sample is a dataclass row.

2. **STRATEGIZE (the LLM drives).** We prompt the LLM (constitution §1: Sonnet 4.6
   on the inner red loop) with the sample + the discovered sensitivity map + the
   intent to preserve + prior attempts. It returns a STRUCTURED attack VECTOR:
   which feature(s), which direction(s), and a rationale (it may combine features
   creatively). The LLM owns the STRATEGY; the sensitivity map makes it INFORMED
   (the meta-attacker failed because it was blind to exactly this). It emits a
   structured vector, NOT code — there is no untrusted-code execution path.

3. **SOLVE (generic numeric search).** On the LLM-chosen feature(s) + direction(s)
   we run a deterministic search (a geometric ladder per feature, all chosen
   features pushed together in the LLM's directions) to find values that drive
   ``score_fn(mutated) < threshold`` while ``label_fn(mutated)`` stays True (intent
   preserved). The first landing wins. If nothing lands, the result is fed back to
   the LLM to RE-STRATEGIZE. Budgeted by ``max_llm_calls`` and ``max_iters``.

**Provenance (transparency).** Every landed attack records the LLM's chosen vector
+ rationale AND that the value was numerically SOLVED (``catalog.record_vector``),
so it is clear the LLM drove the strategy and the solver refined the value — not a
script masquerading as the model.

**Target-agnostic by construction.** This module imports ONLY ``shared.*`` and
``orchestrator.interfaces``, names ZERO target-specific fields (a source-grep test
asserts this), and receives every target-shaped thing by INJECTION — the provider,
``score_fn``, the intent ``label_fn``, the threshold, and the spec. It conforms to
the ``Adversary`` Protocol (``mutate(sample, score) -> object | None``) so it drops
into the existing loop unchanged.

It fails loud on malformed provider output (no fabricated mutation).
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from shared.llm.base import LLMProvider
from shared.types import SealedSpec

from modules.red.catalog import StrategyCatalog

# Probe step (fraction of a field's current value) used to estimate sensitivity.
# Small so the probe stays near the operating point; a field at zero is probed
# with an absolute step so it is not silently skipped.
_PROBE_FRACTION = 0.1
_PROBE_ABSOLUTE = 1.0
# A score delta below this (in magnitude) is treated as "field does not move the
# score" — keeps the sensitivity map to the fields actually worth attacking.
_SENSITIVITY_EPSILON = 1e-9
# The solve ladder: geometric multipliers applied toward the chosen direction.
# Decrease drives a field toward zero; increase drives it upward. Fine enough to
# land most evasions, bounded so a non-landing search terminates cheaply.
_DECREASE_LADDER = (0.5, 0.25, 0.1, 0.05, 0.02, 0.0)
_INCREASE_LADDER = (1.5, 2.0, 4.0, 8.0, 16.0)


_SYSTEM = (
    "You are a red-team adversary probing a deployed model for blind spots. A "
    "sample was CAUGHT by the target (its score is at or above the decision "
    "threshold). You have already PROBED the target: you will be shown a "
    "SENSITIVITY MAP saying, for each numeric field, how much the target's score "
    "moves when that field is nudged up or down, and which direction LOWERS the "
    "score.\n\n"
    "Your job is STRATEGY, not arithmetic. Choose an attack VECTOR: which "
    "field(s) to move and in which direction (\"increase\" or \"decrease\") to "
    "drive the score down, while the sample stays a genuine true positive (the "
    "INTENT must be preserved). You are FREE to pick one field or COMBINE several "
    "creatively; lean on the sensitivity map to pick fields that actually move "
    "the score in the helpful direction. Do NOT pick exact numbers — a "
    "deterministic solver will find the landing values along the directions you "
    "choose. Return the chosen (field, direction) moves plus a one-sentence "
    "rationale."
)

_VECTOR_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "moves": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string"},
                    "direction": {"type": "string", "enum": ["increase", "decrease"]},
                },
                "required": ["feature", "direction"],
                "additionalProperties": False,
            },
        },
        "rationale": {"type": "string"},
    },
    "required": ["moves", "rationale"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class _Sensitivity:
    """How one numeric field moves the target's score around the sample.

    ``lowering_direction`` is "increase" or "decrease" — the direction that DROPS
    the score (the helpful direction for an evasion), or ``None`` if neither
    perturbation moved the score meaningfully. ``magnitude`` is the larger of the
    up/down absolute score deltas (how strongly the field matters).
    """

    feature: str
    lowering_direction: str | None
    magnitude: float


def _numeric_fields(sample: object) -> dict[str, float]:
    """The sample's numeric fields as ``{name: value}``.

    Discovered generically via ``dataclasses.asdict`` — NO target field names. Bool
    fields are excluded (they are not the continuous knobs a numeric solver lands).
    """
    if not (dataclasses.is_dataclass(sample) and not isinstance(sample, type)):
        raise TypeError(
            "DiscoverStrategizeSolveAdversary needs a dataclass sample; got "
            f"{type(sample).__name__}"
        )
    row = dataclasses.asdict(cast(Any, sample))
    return {
        name: float(value)
        for name, value in row.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }


class DiscoverStrategizeSolveAdversary:
    """Probe-discovered surface + LLM-chosen vector + generic numeric solver.

    Conforms to the ``Adversary`` Protocol. Fully in-process (no sandbox, no
    LLM-written code — the LLM emits a STRUCTURED vector). Everything
    target-shaped is INJECTED:

    * ``provider`` — the LLM (Sonnet 4.6 per §1) that chooses the attack vector.
    * ``score_fn`` — the target's score for a candidate sample (the probe queries
      this; the solver drives it below ``threshold``).
    * ``label_fn`` — the intent oracle: does the mutated sample stay a true
      positive? (e.g. the fraud reference model's ``reference_is_fraud``.)
    * ``threshold`` — the target's decision threshold (clears iff score below it).
    * ``spec`` — surfaced to the LLM as context (intent description). No field
      names are read from it.

    There is NO ``movable_features`` parameter: the surface is DISCOVERED by the
    probe. Budgeted by ``max_llm_calls`` (provider calls) and ``max_iters``
    (strategize->solve rounds).
    """

    def __init__(
        self,
        provider: LLMProvider,
        spec: SealedSpec,
        score_fn: Callable[[object], float],
        label_fn: Callable[[object], bool],
        threshold: float,
        *,
        intent_description: str = (
            "Keep the sample a genuine true positive — the same true label it has "
            "now must still hold after your mutation."
        ),
        max_iters: int = 3,
        max_llm_calls: int | None = None,
        catalog: StrategyCatalog | None = None,
    ) -> None:
        self._provider = provider
        self._spec = spec
        self._score = score_fn
        self._is_positive = label_fn
        self._threshold = threshold
        self._intent = intent_description
        self._max_iters = max_iters
        self._max_llm_calls = max_llm_calls
        self._catalog = catalog
        self._calls_made = 0

    @property
    def calls_made(self) -> int:
        return self._calls_made

    # --- Adversary Protocol ------------------------------------------------

    def mutate(self, sample: object, score: float) -> object | None:
        """Run discover -> (strategize -> solve)* until an evasion lands or budget
        is spent. Returns the landed mutated sample, else ``None``."""
        baseline = _numeric_fields(sample)
        sensitivity = self.discover(sample, baseline)
        if not any(s.lowering_direction is not None for s in sensitivity.values()):
            return None  # nothing the target is sensitive to — honest no-evasion

        history: list[str] = []
        for _ in range(self._max_iters):
            if self._max_llm_calls is not None and self._calls_made >= self._max_llm_calls:
                return None
            self._calls_made += 1
            directions, rationale, reject = self._strategize(
                sample, score, sensitivity, baseline, history
            )
            if reject is not None:
                history.append(reject)
                continue

            landed = self.solve(sample, baseline, directions)
            if landed is not None:
                self._record(directions, rationale, solved=True)
                return landed

            history.append(
                f"Vector {directions} (rationale: {rationale!r}) did not land: the "
                "solver could not drive the score below the threshold while keeping "
                "the intent. Try other field(s)/direction(s) from the sensitivity map."
            )
        return None

    # --- DISCOVER ----------------------------------------------------------

    def discover(
        self, sample: object, baseline: Mapping[str, float]
    ) -> dict[str, _Sensitivity]:
        """Probe every numeric field up and down; build the sensitivity map.

        For each field we perturb it by a small step (relative, or absolute when
        the value is ~0) in both directions, query ``score_fn``, and record which
        direction LOWERS the score and how strongly the field matters. Pure
        introspection + target queries — no target field names.
        """
        base_score = self._score(sample)
        out: dict[str, _Sensitivity] = {}
        for name, value in baseline.items():
            step = abs(value) * _PROBE_FRACTION or _PROBE_ABSOLUTE
            up = self._score(self._with(sample, {name: value + step}))
            down = self._score(self._with(sample, {name: value - step}))
            d_up = up - base_score   # increasing the field changes score by d_up
            d_down = down - base_score
            out[name] = _Sensitivity(
                feature=name,
                lowering_direction=self._lowering_direction(d_up, d_down),
                magnitude=max(abs(d_up), abs(d_down)),
            )
        return out

    @staticmethod
    def _lowering_direction(d_up: float, d_down: float) -> str | None:
        """Which perturbation direction lowered the score the most (or None)."""
        best = min(d_up, d_down)
        if best >= -_SENSITIVITY_EPSILON:
            return None  # neither direction lowered the score
        return "increase" if d_up <= d_down else "decrease"

    # --- STRATEGIZE --------------------------------------------------------

    def _strategize(
        self,
        sample: object,
        score: float,
        sensitivity: Mapping[str, _Sensitivity],
        baseline: Mapping[str, float],
        history: list[str],
    ) -> tuple[dict[str, str], str, str | None]:
        """Ask the LLM for a structured attack vector (features + directions).

        Returns ``(directions, rationale, None)`` on a valid vector, or
        ``({}, "", reject_reason)`` so the caller appends the reason and retries.
        """
        resp = self._provider.complete(
            self._build_prompt(sample, score, sensitivity, baseline, history),
            system=_SYSTEM,
            max_tokens=512,
            json_schema=_VECTOR_SCHEMA,
        )
        parsed = json.loads(resp.text)  # fail loud on malformed provider output
        if not isinstance(parsed, dict):
            return {}, "", "Rejected vector: top-level JSON must be an object."
        raw_moves = parsed.get("moves")
        if not isinstance(raw_moves, list) or not raw_moves:
            return {}, "", "Rejected vector: 'moves' must be a non-empty list."
        directions: dict[str, str] = {}
        for item in raw_moves:
            if not isinstance(item, dict):
                return {}, "", "Rejected vector: each move must be an object."
            feat = str(item.get("feature"))
            direction = item.get("direction")
            if feat not in baseline:
                return {}, "", (
                    f"Rejected move feature={feat!r}: must be one of the numeric "
                    "fields shown in the sensitivity map."
                )
            if direction not in ("increase", "decrease"):
                return {}, "", (
                    f"Rejected move feature={feat!r}: direction must be "
                    "'increase' or 'decrease'."
                )
            directions[feat] = direction
        rationale = str(parsed.get("rationale", "")).strip()
        return directions, rationale, None

    def _build_prompt(
        self,
        sample: object,
        score: float,
        sensitivity: Mapping[str, _Sensitivity],
        baseline: Mapping[str, float],
        history: list[str],
    ) -> str:
        rows = sorted(
            sensitivity.values(), key=lambda s: (-s.magnitude, s.feature)
        )
        lines = [
            f"- {s.feature}: current={baseline[s.feature]:g}, "
            + (
                f"moving it {s.lowering_direction} LOWERS the score "
                f"(score-sensitivity magnitude {s.magnitude:.4g})"
                if s.lowering_direction is not None
                else "the score is INSENSITIVE to this field (skip it)"
            )
            for s in rows
        ]
        prompt = (
            "Sample numeric fields:\n"
            f"{json.dumps({k: round(v, 4) for k, v in baseline.items()}, indent=2)}\n\n"
            f"Target decision: CAUGHT (score={score} >= threshold={self._threshold}).\n\n"
            "SENSITIVITY MAP (probed by nudging each field up/down):\n"
            + "\n".join(lines)
            + "\n\nIntent to preserve:\n"
            + self._intent
            + "\n\nChoose the attack vector: which field(s) to move and in which "
            "direction to drive the score below the threshold while preserving the "
            "intent. Prefer fields whose lowering direction matches your move; "
            "combining several is encouraged. A solver will land the values."
        )
        if history:
            prompt += (
                "\n\nPrior vectors this round (learn from them, do not repeat):\n"
                + "\n".join(f"- {h}" for h in history)
            )
        return prompt

    # --- SOLVE -------------------------------------------------------------

    def solve(
        self,
        sample: object,
        baseline: Mapping[str, float],
        directions: Mapping[str, str],
    ) -> object | None:
        """Deterministically land the LLM's vector.

        Walks a shared geometric ladder, pushing EVERY chosen feature toward its
        LLM-chosen direction simultaneously. The first rung where the target
        CLEARS (``score < threshold``) AND the intent is preserved
        (``label_fn`` True) wins. Returns the mutated sample, else ``None`` (the
        caller feeds this back to the LLM to re-strategize).
        """
        # All chosen features share a step index so a multi-feature vector is a
        # genuine combined move (not independently optimized axes).
        ladders = {
            feat: (
                _DECREASE_LADDER if direction == "decrease" else _INCREASE_LADDER
            )
            for feat, direction in directions.items()
        }
        rungs = min(len(ladder) for ladder in ladders.values())
        for rung in range(rungs):
            changes = {
                feat: round(baseline[feat] * ladders[feat][rung], 4)
                for feat in directions
            }
            candidate = self._with(sample, changes)
            if not self._is_positive(candidate):
                continue  # broke the intent at this rung — push less / try next
            if self._score(candidate) < self._threshold:
                return candidate
        return None

    # --- helpers -----------------------------------------------------------

    @staticmethod
    def _with(sample: object, changes: Mapping[str, float]) -> object:
        """A copy of the dataclass sample with ``changes`` applied (generic)."""
        return dataclasses.replace(cast(Any, sample), **changes)

    def _record(
        self, directions: Mapping[str, str], rationale: str, *, solved: bool
    ) -> None:
        if self._catalog is None:
            return
        self._catalog.record_vector(dict(directions), rationale, solved=solved)
