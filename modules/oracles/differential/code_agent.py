"""Code-agent differential oracle (PR3 port B2): a SECOND implementation from a different
model family solves the same task; both run in the sealed sandbox and their results are
compared. A disagreement is flagged WITHOUT declaring either side correct, the platform
never trusts a single side as ground truth (ARCHITECTURE.md decision table).

Adapted to main's stdout-based CodeAgentTarget. Main's code agent writes a COMPLETE script
that prints its results to stdout, so the "same inputs, compare outputs" check is a stdout
diff: the reference coder solves the same task, its script runs in the same sandbox, and
the oracle fires when the reference's stdout differs from the producer's. The second
implementation's source is carried on the vote so the verdict drawer can show it.

Julian's FraudDifferentialOracle (LightGBM vs IsolationForest) is untouched; this is the
code-agent sibling.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from shared.llm.client import LLMClient
from shared.sandbox.local import SandboxResult
from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec

_INPUT_KEYS = ("input", "prompt", "task", "message", "text")
_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


@runtime_checkable
class CodeRunner(Protocol):
    """The sealed sandbox the producer ran in (structural type, so the oracle does not
    import the targets module — module-boundary rule, F2)."""

    async def run(
        self, main_script: str, *, files: Mapping[str, str] | None = ...,
        argv: list[str] | None = ...,
    ) -> SandboxResult: ...


def extract_code(text: str) -> str:
    """Pull the Python out of a model reply — the code fence if present, else the whole text."""
    match = _FENCE.search(text)
    return (match.group(1) if match else text).strip()
_REFERENCE_SYSTEM = (
    "You are a careful Python engineer. Given a task, output a COMPLETE Python script "
    "(only code, no markdown, no prose) that solves it and prints its results to stdout, "
    "exactly as a correct solution should."
)


def _task(payload: Mapping[str, Any]) -> str:
    for key in _INPUT_KEYS:
        value = payload.get(key)
        if value is not None:
            return str(value)
    return str(dict(payload))


@dataclass(frozen=True, slots=True)
class CodeDifferentialOracle:
    """Cross-family agreement check for code producers: a reference model writes a second
    implementation of the same task and the two are run and compared."""

    _llm: LLMClient        # the REFERENCE coder; a different model family from the producer
    _runner: CodeRunner    # the same sealed sandbox the producer ran in
    kind: OracleKind = OracleKind.differential
    weight: float = 1.0

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        producer_stdout = str(output.get("stdout", "")).strip()
        task = _task(attack.payload)
        result = await self._llm.complete(_REFERENCE_SYSTEM, task, max_tokens=900)
        reference_code = extract_code(result.text)
        if not reference_code.strip():
            return OracleVote(
                oracle=self.kind, fired=False, weight=self.weight,
                obligation="the producer's output must match an independent second implementation",
                observation=f"reference_model={result.model} produced no code",
                reason="differential unavailable: the reference produced no implementation",
                dollars=result.dollars, seed=attack.seed, available=False,
            )
        sandbox = await self._runner.run(reference_code)
        reference_stdout = sandbox.stdout.strip()
        diverged = reference_stdout != producer_stdout
        observation = (
            f"Second implementation ({result.model}):\n{reference_code}\n"
            f"--- reference stdout ---\n{reference_stdout[:400]}\n"
            f"--- producer stdout ---\n{producer_stdout[:400]}"
        )
        reason = (
            "Producer and the independent second implementation DIVERGED on the same task "
            "(their stdout differs); a different model family disagrees with the producer."
            if diverged else
            "Producer and the independent second implementation AGREED on the same task."
        )
        return OracleVote(
            oracle=self.kind, fired=diverged, weight=self.weight,
            obligation="the producer's output must match an independent second implementation",
            observation=observation, reason=reason,
            dollars=result.dollars, seed=attack.seed,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green",
            detail={"oracle": "differential", "mode": "code-second-implementation"},
        )
