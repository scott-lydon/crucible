"""Real LLM-judge oracle.

An independent, skeptical assessor: it does not re-run the detector, it forms
its OWN opinion of whether a sample the detector CLEARED is actually a positive
the detector missed. The LLM provider is INJECTED (constitution §1: real Opus
4.8 in the demo, a deterministic ``MockProvider`` test double in unit tests), so
the oracle stays vendor-agnostic and offline-testable.

The oracle is 100% TARGET-AGNOSTIC: this source file contains NO domain words.
Every scrap of target-specific meaning flows in at runtime as DATA from the
injected ``SealedSpec`` (its declared obligations, invariants, and metamorphic
relations are rendered generically here). The deterministic ``InvariantOracle``
remains the hard checker; this judge ADDS reasoning — beyond re-checking the
declared obligations it independently hunts for missed positives the
declarations might not capture.

Per plan §3 the judge casts a single 0.5-weight vote ("one vote", deliberately
less than the full-weight ground-truth/differential oracles). It fails loud:
provider or parse errors propagate rather than collapsing into a fake PASS.
"""

import dataclasses
import json
from collections.abc import Mapping, Sequence

from shared.llm.base import LLMProvider
from shared.types import OracleKind, OracleVote, VerdictContext, Vote

_JUDGE_WEIGHT = 0.5  # plan §3: "one vote", half the weight of a hard oracle.

_SYSTEM = (
    "You are an independent auditor in a sealed evaluation. You assess one "
    "sample that an automated target classified. Adopt a skeptical stance: you "
    "do NOT trust the target's decision, because a plausible-looking clearance "
    "is exactly what a flawed target produces. Your duty is to the declared "
    "obligations and to catching what the target got wrong, not to ratifying it. "
    "When the evidence supports a violation you vote FAIL and do NOT give the "
    "target the benefit of the doubt; you only vote PASS when nothing in the "
    "evidence indicates a violation or a missed positive. Reason solely from the "
    "data supplied to you — the sample, the target's decision, and the declared "
    "obligations — making no assumptions about the domain beyond that data."
)

# Structured output: per-obligation findings + an independent lane-(b) finding +
# the final vote. We fail loud if the provider returns anything else.
_VOTE_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "per_obligation": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "triggered": {"type": "boolean"},
                    "consistent": {"type": "boolean"},
                },
                "required": ["id", "triggered", "consistent"],
                "additionalProperties": False,
            },
        },
        "independent_finding": {"type": "string"},
        "vote": {"type": "string", "enum": ["pass", "fail"]},
        "reason": {"type": "string"},
    },
    "required": ["per_obligation", "independent_finding", "vote", "reason"],
    "additionalProperties": False,
}


def _as_fields(item: object) -> dict[str, object]:
    """Render a declared spec item's fields generically — by introspection, never
    by naming any field. Frozen dataclasses become their field dict; anything
    else degrades to a stable ``repr``."""
    if dataclasses.is_dataclass(item) and not isinstance(item, type):
        return dataclasses.asdict(item)
    return {"value": repr(item)}


def _features(sample: object) -> Mapping[str, object]:
    # The sample is an opaque frozen dataclass; serialize generically.
    if dataclasses.is_dataclass(sample) and not isinstance(sample, type):
        return dataclasses.asdict(sample)
    return {"sample": repr(sample)}


def _declared_obligations(ctx: VerdictContext) -> Sequence[Mapping[str, object]]:
    """Render the spec's declared items into a generic, id'd list — by iterating
    whatever the spec exposes, never by hardcoding any obligation text or field.

    Each declared invariant, metamorphic relation, and free-text obligation
    becomes one entry with a stable ``id`` plus a generic dict of its declared
    fields, so the model can reason about each one without this module knowing
    anything about the domain it describes.
    """
    items: list[Mapping[str, object]] = []
    spec = ctx.spec

    for inv in getattr(spec, "invariants", ()):  # typed declared items
        fields = _as_fields(inv)
        ident = str(fields.pop("name", f"invariant_{len(items)}"))
        items.append({"id": ident, "declaration": fields})

    for rel in getattr(spec, "metamorphic_relations", ()):
        fields = _as_fields(rel)
        ident = str(fields.pop("name", f"relation_{len(items)}"))
        items.append({"id": ident, "declaration": fields})

    # Free-text obligations (if the spec exposes them) get synthesized ids.
    for i, text in enumerate(getattr(spec, "obligations", ())):
        items.append({"id": f"obligation_{i}", "declaration": {"statement": str(text)}})

    return items


def _build_prompt(ctx: VerdictContext) -> str:
    features: Mapping[str, object] = _features(ctx.sample)
    obligations = _declared_obligations(ctx)
    numbered = "\n".join(
        f"{i + 1}. id={item['id']!r}: {json.dumps(item['declaration'], default=str)}"
        for i, item in enumerate(obligations)
    )
    cleared = ctx.detector_score < ctx.threshold
    decision = "cleared (classified negative)" if cleared else "flagged (classified positive)"
    return (
        "Sample under review (its raw fields):\n"
        f"{json.dumps(features, indent=2, default=str)}\n\n"
        f"Target's decision: {decision} "
        f"(score={ctx.detector_score}, threshold={ctx.threshold}; "
        "a score below the threshold is a negative classification).\n\n"
        "Declared obligations (data; reason from these, do not assume more):\n"
        f"{numbered if numbered else '(none declared)'}\n\n"
        "Do TWO things and report both:\n"
        "(a) For EACH declared obligation above, decide whether THIS sample "
        "triggers it and whether the target's decision is consistent with it. "
        "Report one entry per obligation, citing its id.\n"
        "(b) INDEPENDENTLY of the declared obligations, judge whether this looks "
        "like a positive the target missed that the obligations might NOT "
        "capture; describe your reasoning in 'independent_finding'.\n\n"
        "Vote 'fail' if ANY declared obligation is violated (triggered but the "
        "decision is inconsistent with it) OR if (b) finds a missed positive; "
        "otherwise vote 'pass'. In 'reason', cite the violated obligation id(s) "
        "or your independent reasoning."
    )


class LlmJudgeOracle:
    """LLM-backed judge oracle. One 0.5-weight, labeled vote per sample."""

    def __init__(self, provider: LLMProvider, max_calls: int | None = None) -> None:
        self._provider = provider
        # Cost bound (plan §6): cap real provider calls per run. ``None`` =
        # unbounded. Beyond the cap the judge ABSTAINS honestly (weight 0) — it
        # does not fabricate a vote — and never touches the provider.
        self._max_calls = max_calls
        self._calls_made = 0

    @property
    def kind(self) -> OracleKind:
        return OracleKind.LLM_JUDGE

    def vote(self, ctx: VerdictContext) -> OracleVote:
        if self._max_calls is not None and self._calls_made >= self._max_calls:
            return OracleVote(
                kind=self.kind,
                vote=Vote.ABSTAIN,
                weight=0.0,
                reason=f"LLM judge budget exhausted ({self._max_calls} calls/run)",
                evidence={"llm": True, "budget_exhausted": True},
            )
        self._calls_made += 1
        resp = self._provider.complete(
            _build_prompt(ctx),
            system=_SYSTEM,
            max_tokens=512,
            json_schema=_VOTE_SCHEMA,
        )
        parsed = json.loads(resp.text)  # fail loud on malformed provider output
        # Fail loud on a structurally wrong payload (no fake PASS): the required
        # keys MUST be present, or the KeyError propagates.
        vote_raw = parsed["vote"]
        per_obligation = parsed["per_obligation"]
        independent_finding = parsed["independent_finding"]
        reason = str(parsed["reason"])
        vote = Vote.FAIL if str(vote_raw).lower() == "fail" else Vote.PASS
        return OracleVote(
            kind=self.kind,
            vote=vote,
            weight=_JUDGE_WEIGHT,
            reason=reason,
            evidence={
                "model": resp.model,
                "input_tokens": resp.input_tokens,
                "output_tokens": resp.output_tokens,
                "dollars": resp.dollars,
                "llm": True,
                "per_obligation": per_obligation,
                "independent_finding": independent_finding,
            },
        )
