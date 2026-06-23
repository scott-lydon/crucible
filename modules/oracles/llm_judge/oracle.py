"""Real LLM-judge oracle.

An independent assessor: it does not re-run the detector, it forms its OWN
opinion of whether a transaction the detector CLEARED is actually fraud the
detector missed. The LLM provider is INJECTED (constitution §1: real Opus 4.8 in
the demo, a deterministic ``MockProvider`` test double in unit tests), so the
oracle stays vendor-agnostic and offline-testable.

Per plan §3 the judge casts a single 0.5-weight vote ("one vote", deliberately
less than the full-weight ground-truth/differential oracles). It fails loud:
provider or parse errors propagate rather than collapsing into a fake PASS.
"""

import dataclasses
import json
from collections.abc import Mapping

from shared.llm.base import LLMProvider
from shared.types import OracleKind, OracleVote, VerdictContext, Vote

_JUDGE_WEIGHT = 0.5  # plan §3: "one vote", half the weight of a hard oracle.

_SYSTEM = (
    "You are an independent fraud-review judge. A fraud detector CLEARED a "
    "transaction (its score fell below the decision threshold), meaning it "
    "judged the transaction NOT fraud. Your job is to assess, on the evidence, "
    "whether that decision is sound or whether this is fraud the detector "
    "missed. Reason from the transaction features and the target's obligations. "
    'Respond with vote="pass" if the detector\'s clear decision is sound, or '
    'vote="fail" if this looks like missed fraud, plus a one-paragraph reason.'
)

_VOTE_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "vote": {"type": "string", "enum": ["pass", "fail"]},
        "reason": {"type": "string"},
    },
    "required": ["vote", "reason"],
    "additionalProperties": False,
}


def _features(sample: object) -> Mapping[str, object]:
    # The sample is an opaque frozen dataclass; serialize generically.
    if dataclasses.is_dataclass(sample) and not isinstance(sample, type):
        return dataclasses.asdict(sample)
    return {"sample": repr(sample)}


def _build_prompt(ctx: VerdictContext) -> str:
    features: Mapping[str, object] = _features(ctx.sample)
    obligations = "\n".join(f"- {o}" for o in ctx.spec.obligations)
    return (
        "Transaction features:\n"
        f"{json.dumps(features, indent=2, default=str)}\n\n"
        "Detector decision: CLEARED as not-fraud "
        f"(detector_score={ctx.detector_score} < threshold={ctx.threshold}).\n\n"
        f"Target obligations the detector must satisfy:\n{obligations}\n\n"
        "Independently assess whether the detector's decision is sound, i.e. is "
        "this transaction actually fraud that the detector missed? Respond "
        "pass = decision sound / fail = missed fraud, with a one-paragraph reason."
    )


class LlmJudgeOracle:
    """LLM-backed judge oracle. One 0.5-weight, labeled vote per sample."""

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    @property
    def kind(self) -> OracleKind:
        return OracleKind.LLM_JUDGE

    def vote(self, ctx: VerdictContext) -> OracleVote:
        resp = self._provider.complete(
            _build_prompt(ctx),
            system=_SYSTEM,
            max_tokens=512,
            json_schema=_VOTE_SCHEMA,
        )
        parsed = json.loads(resp.text)  # fail loud on malformed provider output
        vote = Vote.FAIL if str(parsed["vote"]).lower() == "fail" else Vote.PASS
        reason = str(parsed.get("reason", ""))
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
            },
        )
