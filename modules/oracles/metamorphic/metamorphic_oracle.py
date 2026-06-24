"""Metamorphic oracle: relations that hold without a reference answer.

Sonnet synthesizes metamorphic relations from the sealed spec (properties that
must hold when an input is transformed, such as commutativity or an increment
law), and those relations run against the producer output in the sealed
sandbox. Needing no reference answer, this catches a producer that is wrong in
a way a fixed test happens not to probe.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

from shared.llm import LlmClient, LlmModel
from shared.sandbox import CheckOutcome, DockerSandbox, run_python_checks
from shared.source import extract_python_source
from shared.types import (
    OracleVote,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    TargetOutput,
    VerdictDecision,
)


@dataclass(frozen=True, slots=True)
class MetamorphicOracle:
    """Synthesizes metamorphic relations and checks them in the sandbox."""

    llm: LlmClient
    sandbox: DockerSandbox
    name: str = "metamorphic"
    weight: float = 1.0
    model: LlmModel = LlmModel.SONNET
    min_rules: int = 3

    @property
    def protocol_description(self) -> str:
        return (
            "Synthesizes at least three metamorphic relations from the spec invariants "
            "(properties that must hold when an input is transformed, with no reference "
            "answer) and checks each in the sealed sandbox; a violated relation is a FAIL."
        )

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
                "metamorphic oracle needs source-code output; this target produced none",
                obligation_id,
            )

        rules = await self.generate_rules(spec)
        if len(rules) < self.min_rules:
            return self._vote(
                VerdictDecision.UNAVAILABLE,
                f"synthesized only {len(rules)} relations; need at least {self.min_rules}",
                obligation_id,
            )

        result = await run_python_checks(self.sandbox, output.output, "\n".join(rules))
        if result.outcome is CheckOutcome.PASS:
            return self._vote(
                VerdictDecision.PASS,
                f"all {len(rules)} metamorphic relations held in the sealed sandbox",
                obligation_id,
            )
        if result.outcome is CheckOutcome.FAIL:
            return self._vote(
                VerdictDecision.FAIL,
                f"a metamorphic relation failed in the sealed sandbox: {result.detail[:300]}",
                obligation_id,
            )
        return self._vote(
            VerdictDecision.UNAVAILABLE,
            f"metamorphic harness errored, inconclusive: {result.detail[:200]}",
            obligation_id,
        )

    async def generate_rules(self, spec: SealedSpec) -> list[str]:
        """Synthesize metamorphic relations as assert statements (one per line)."""
        invariants = "\n".join(f"- {i.id}: {i.description}" for i in spec.invariants)
        if not invariants:
            invariants = "(none stated; derive sensible relations from the obligations)"
        obligations = "\n".join(f"- {o.id}: {o.description}" for o in spec.obligations)
        prompt = (
            "You are an independent verifier using metamorphic testing. A Python "
            "implementation is defined above your code in the same module. Write at "
            "least three Python assert statements, each encoding a metamorphic "
            "relation: a property that must hold when an input is transformed, "
            "needing no reference answer (for example commutativity, or that adding "
            "one to an input adds one to the output). Use concrete literal inputs in "
            "every assert, for example `assert add(2, 3) == add(3, 2)`. Every name "
            "besides the implementation's own functions must be a literal: do not "
            "reference undefined variables like a or b. Output ONLY assert statements, "
            "one per line: no imports, no markdown, no definitions, no explanation.\n\n"
            f"Obligations:\n{obligations}\n\nInvariants:\n{invariants}\n"
        )
        result = await self.llm.call(prompt, model=self.model)
        text = extract_python_source(result.text)
        return [line.strip() for line in text.splitlines() if line.strip().startswith("assert")]

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

    async def self_test(self) -> ProbeResult:
        """Readiness probe: needs an LLM client and a docker daemon."""
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
