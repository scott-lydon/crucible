"""LLM judge oracle: Opus reads the output and votes pass / fail.

The fifth member of the verification ensemble, and deliberately the weakest.
It is one large language model reading the produced artifact against the
sealed spec's obligations and voting, with a one-paragraph reason. The
proposal includes a large language model judge "as one measured approach
among several, never the sole authority" (proposal section 3, Pillar 1).

It carries half a vote (0.5), so on its own it can never carry a verdict past
the aggregator's 2.0 pass threshold (ARCHITECTURE.md section 3). The four
mechanical oracles do the load-bearing work; the judge is measured alongside
them so the verdict view can mark it "one vote" (US-4) and the dashboard can
report how often the judge agrees with the ensemble it cannot overrule.

Unlike the other four oracles, the judge runs nothing in the sandbox: it
reads the artifact and reasons, so it needs no docker daemon, only the LLM
client.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from typing import Any

from shared.llm import LlmClient, LlmModel
from shared.types import (
    OracleVote,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    TargetOutput,
    VerdictDecision,
)

# How much of a large artifact to show the judge. A code submission is far
# under this; the cap only guards against an unbounded artifact inflating the
# prompt (and the call cost) without changing the verdict. It is intentionally
# generous so the judge sees the whole of any realistic submission.
_MAX_ARTIFACT_CHARS = 20_000


def _extract_json_object(text: str) -> str | None:
    """Return the first ``{...}`` JSON object substring, fenced or bare.

    The judge is told to return bare JSON but a model sometimes wraps it in a
    ```json fence anyway, so the fence is stripped first. Returns None when no
    brace-delimited object is present, so the caller votes UNAVAILABLE rather
    than guessing.
    """
    stripped = text.strip()
    if "```" in stripped:
        stripped = stripped.split("```", 2)[1]
        if stripped.startswith("json"):
            stripped = stripped[len("json") :]
        stripped = stripped.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    return stripped[start : end + 1]


def parse_judge_response(text: str) -> tuple[VerdictDecision, str] | None:
    """Pull a ``{"decision", "reason"}`` verdict out of the judge's response.

    Returns the decision and its reason, or None when the response is not a
    parseable pass / fail verdict. The oracle turns None into an UNAVAILABLE
    vote, never a guessed pass or fail (ARCHITECTURE.md section 3 failure
    modes): a judge that did not answer in the required shape is an unavailable
    vote, not a silent verdict.
    """
    blob = _extract_json_object(text)
    if blob is None:
        return None
    try:
        data: Any = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    decision_raw = data.get("decision")
    reason_raw = data.get("reason")
    if not isinstance(decision_raw, str) or not isinstance(reason_raw, str):
        return None
    decision = decision_raw.strip().lower()
    reason = reason_raw.strip()
    if not reason:
        return None
    if decision == "pass":
        return VerdictDecision.PASS, reason
    if decision == "fail":
        return VerdictDecision.FAIL, reason
    return None


@dataclass(frozen=True, slots=True)
class LlmJudgeOracle:
    """One large language model reading the artifact and voting at half weight."""

    llm: LlmClient
    name: str = "llm_judge"
    weight: float = 0.5
    model: LlmModel = LlmModel.OPUS

    async def verify(
        self,
        spec: SealedSpec,
        attack_input: dict[str, Any],
        output: TargetOutput,
    ) -> OracleVote:
        obligation_id = spec.obligations[0].id if spec.obligations else None
        rendered = self._render_artifact(output.output)
        if not rendered.strip():
            return self._vote(
                VerdictDecision.UNAVAILABLE,
                "the producer returned an empty artifact; the judge had nothing to read",
                obligation_id,
            )

        response = await self.llm.call(self._prompt(spec, rendered), model=self.model)
        parsed = parse_judge_response(response.text)
        if parsed is None:
            return self._vote(
                VerdictDecision.UNAVAILABLE,
                "the judge response was not a parseable pass/fail verdict: "
                f"{response.text[:200]}",
                obligation_id,
            )

        decision, reason = parsed
        return self._vote(decision, reason, obligation_id)

    def _vote(
        self, decision: VerdictDecision, reason: str, obligation_id: str | None
    ) -> OracleVote:
        return OracleVote(
            oracle_name=self.name,
            decision=decision,
            weight=self.weight,
            reason=reason,
            obligation_id=obligation_id,
        )

    @staticmethod
    def _render_artifact(output: Any) -> str:
        """Render any target's output as text for the judge to read.

        A code submission is already a string. A fraud score or any structured
        output is JSON-serialized so the judge is target-agnostic (it reads
        whatever the target produced), with str() as the last-resort fallback
        for a value JSON cannot encode.
        """
        text = output if isinstance(output, str) else _to_json_text(output)
        if len(text) > _MAX_ARTIFACT_CHARS:
            return text[:_MAX_ARTIFACT_CHARS] + "\n... [artifact truncated for the judge]"
        return text

    def _prompt(self, spec: SealedSpec, rendered: str) -> str:
        obligations = "\n".join(f"- {o.id}: {o.description}" for o in spec.obligations)
        return (
            "You are one independent judge in a verification ensemble. Read the "
            "produced artifact below and decide whether it satisfies every "
            "obligation. You are not the sole authority and you cannot override "
            "the other checks; vote honestly on what you see. Respond with ONLY "
            'a JSON object of the form {"decision": "pass" | "fail", "reason": '
            '"<one paragraph>"}. No markdown fences, no text outside the object.'
            "\n\n"
            f"Title: {spec.title}\n"
            f"Obligations:\n{obligations}\n\n"
            f"Produced artifact:\n{rendered}\n"
        )

    async def self_test(self) -> ProbeResult:
        """Readiness probe: needs an LLM client, no docker (the judge runs nothing).

        Green when the real CLI is on PATH or a scripted client is wired
        (the mock-LLM path of US-15), amber otherwise so the /health page shows
        the judge cannot reach the model yet rather than failing a run silently.
        """
        has_cli = shutil.which("claude") is not None
        scripted = type(self.llm).__name__ == "ScriptedLlmClient"
        ready = has_cli or scripted
        return ProbeResult(
            status=ProbeStatus.GREEN if ready else ProbeStatus.AMBER,
            detail={
                "name": self.name,
                "model": self.model.value,
                "client": type(self.llm).__name__,
                "claude_cli": has_cli,
            },
        )


def _to_json_text(output: Any) -> str:
    """JSON-serialize an artifact for the judge, falling back to str on failure."""
    try:
        return json.dumps(output, default=str, sort_keys=True)
    except (TypeError, ValueError):
        return str(output)
