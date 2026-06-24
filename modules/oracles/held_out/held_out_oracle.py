"""Held-out oracle: fresh tests generated after submission.

Opus generates assert-based tests from the sealed spec *after* the producer
has submitted, so a static held-out set cannot leak over time. The tests run
against the producer output inside the sealed sandbox (no network, no host
env), and the oracle votes pass or fail with a reason. It never trusts the
producer: the tests come from the spec, not from the submission.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from shared.llm import LlmClient, LlmModel
from shared.sandbox import DockerSandbox
from shared.source import extract_python_source
from shared.types import (
    OracleVote,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    TargetOutput,
    VerdictDecision,
)

# Printed by the composed script only if every held-out assertion passed.
_PASS_MARKER = "__CRUCIBLE_HELDOUT_PASS__"


@dataclass(frozen=True, slots=True)
class HeldOutOracle:
    """Generates held-out tests from the spec and runs them in the sandbox."""

    llm: LlmClient
    sandbox: DockerSandbox
    name: str = "held_out"
    weight: float = 1.0
    model: LlmModel = LlmModel.OPUS

    async def verify(
        self,
        spec: SealedSpec,
        attack_input: dict[str, Any],
        output: TargetOutput,
    ) -> OracleVote:
        obligation_id = spec.obligations[0].id if spec.obligations else None
        if not isinstance(output.output, str):
            return self._vote(
                VerdictDecision.UNAVAILABLE,
                "held-out oracle needs source-code output; this target produced none",
                obligation_id,
            )

        tests = await self._generate_tests(spec)
        if not tests.strip():
            return self._vote(
                VerdictDecision.UNAVAILABLE,
                "the model produced no held-out assertions to run",
                obligation_id,
            )

        script = (
            f"{output.output}\n\n# --- held-out tests ---\n{tests}\n\n"
            f"print({_PASS_MARKER!r})\n"
        )
        result = await self.sandbox.run_python(script)
        if result.exit_code == 0 and _PASS_MARKER in result.stdout:
            return self._vote(
                VerdictDecision.PASS,
                "all held-out tests passed in the sealed sandbox",
                obligation_id,
            )
        stderr = result.stderr.strip()
        tail = stderr.splitlines()[-1] if stderr else f"exit {result.exit_code}"
        return self._vote(
            VerdictDecision.FAIL,
            f"held-out tests failed in the sealed sandbox: {tail[:300]}",
            obligation_id,
        )

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

    async def _generate_tests(self, spec: SealedSpec) -> str:
        obligations = "\n".join(f"- {o.id}: {o.description}" for o in spec.obligations)
        prompt = (
            "You are an independent verifier. A Python implementation will be "
            "defined above your code in the same module. Write Python assert "
            "statements that check that implementation against the obligations "
            "below. Output ONLY assert statements: no imports, no markdown "
            "fences, no function or class definitions, no explanation.\n\n"
            f"Obligations:\n{obligations}\n"
        )
        result = await self.llm.call(prompt, model=self.model)
        return extract_python_source(result.text)

    async def self_test(self) -> ProbeResult:
        """Readiness probe: needs an LLM client and a docker daemon to run tests."""
        has_docker = shutil.which("docker") is not None
        return ProbeResult(
            status=ProbeStatus.GREEN if has_docker else ProbeStatus.AMBER,
            detail={
                "name": self.name,
                "model": self.model.value,
                "client": type(self.llm).__name__,
                "docker": has_docker,
            },
        )
