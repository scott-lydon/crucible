"""CodeAgentTarget: a Shape 2 target that produces Python source via Claude.

Given a sealed spec, it prompts the LLM (Sonnet by default) to implement the
spec as a Python module and returns the source. The score is the syntactic
validity of that source (1.0 if it parses, 0.0 otherwise), a real signal the
red agent can probe. Execution of the produced code inside the sealed sandbox
lands in slice 4; this slice only produces.
"""

from __future__ import annotations

import ast
import json
import shutil
from dataclasses import dataclass
from typing import Any

from shared.llm import LlmClient, LlmModel, ScriptedLlmClient
from shared.types import (
    AuditStep,
    AuditTrace,
    Obligation,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    SpecId,
    TargetOutput,
    TargetType,
)


def extract_python_source(text: str) -> str:
    """Pull Python source out of a model response, fenced or not.

    The producer is told to return bare source, but models sometimes wrap it
    in a ```python fence anyway, so this strips the first fenced block when
    present and otherwise returns the trimmed text.
    """
    stripped = text.strip()
    if "```" in stripped:
        block = stripped.split("```", 2)[1]
        if block.startswith("python"):
            block = block[len("python") :]
        return block.strip()
    return stripped


def is_valid_python(source: str) -> bool:
    """True when the source parses as Python (the slice-3 done-criterion check)."""
    try:
        ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return True


def _build_prompt(spec: SealedSpec, attack_input: dict[str, Any]) -> str:
    obligations = "\n".join(f"- {o.id}: {o.description}" for o in spec.obligations)
    return (
        "You are a code-producing agent. Implement the specification below as a "
        "single Python module. Return ONLY Python source code: no prose, no "
        "explanation, no markdown fences.\n\n"
        f"Title: {spec.title}\n"
        f"Obligations:\n{obligations}\n"
        f"Task input: {json.dumps(attack_input)}\n"
    )


def _task_spec_from_input(attack_input: dict[str, Any]) -> SealedSpec:
    """Synthesize a minimal spec from a probe input for query_target.

    query_target carries an input but no spec, so a probe of "does the producer
    emit valid code for this input" needs a spec built from the input itself.
    """
    task = attack_input.get("task")
    title = task if isinstance(task, str) and task else "produce code for the given input"
    return SealedSpec(
        spec_id=SpecId.new(),
        title=title,
        obligations=(Obligation(id="o1", description="implement the requested task"),),
        invariants=(),
        holdout_generator_kind="llm_post_submit",
    )


@dataclass(frozen=True, slots=True)
class CodeAgentTarget:
    """Produces Python source for a sealed spec via the LLM."""

    llm: LlmClient
    model: LlmModel = LlmModel.SONNET
    # An instance field (not ClassVar) so it satisfies the Target Protocol's
    # instance-variable member, matching how DummyTarget exposes target_type.
    target_type: TargetType = TargetType.CODE_AGENT

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> TargetOutput:
        """Generate Python source for the spec and return it with a validity score."""
        result = await self.llm.call(_build_prompt(spec, attack_input), model=self.model)
        source = extract_python_source(result.text)
        valid = is_valid_python(source)
        audit = AuditTrace(
            summary="code agent produced Python source via the LLM",
            steps=(
                AuditStep(
                    label="generate",
                    detail={
                        "model": self.model.value,
                        "dollars": str(result.dollars),
                        "tokens_out": result.tokens_out,
                        "valid_python": valid,
                    },
                ),
                AuditStep(label="source", detail={"chars": len(source)}),
            ),
        )
        return TargetOutput(output=source, score=1.0 if valid else 0.0, audit=audit)

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        """Probe: 1.0 if the producer emits valid Python for this input, else 0.0."""
        output = await self.submit(_task_spec_from_input(attack_input), attack_input)
        return output.score if output.score is not None else 0.0

    async def self_test(self) -> ProbeResult:
        """Fast readiness probe.

        A full "produce hello world" round trip is seconds and spends quota, so
        health does not call the model on every poll. It reports the wired
        client and model, and for the real CLI client whether `claude` is on
        PATH (amber when it is not, since calls would then fail).
        """
        detail: dict[str, Any] = {"model": self.model.value, "client": type(self.llm).__name__}
        if isinstance(self.llm, ScriptedLlmClient):
            return ProbeResult(status=ProbeStatus.GREEN, detail={**detail, "mode": "mock"})
        on_path = shutil.which("claude") is not None
        return ProbeResult(
            status=ProbeStatus.GREEN if on_path else ProbeStatus.AMBER,
            detail={**detail, "claude_on_path": on_path},
        )
