"""Property-fuzz oracle: random-sampling property checks in the sealed sandbox.

Sonnet writes a `fuzz()` function that samples many random inputs and asserts
properties the spec guarantees. It runs against the producer output in the
sealed sandbox via the shared check runner, so a violated property (an
AssertionError on some sampled input) is a real FAIL, while a malformed fuzz
harness is inconclusive (UNAVAILABLE), never a false accusation.

The Hypothesis library is not used inside the sandbox: the sandbox denies all
network (`--network none`), so it cannot install hypothesis, and bundling a
hypothesis image is deferred. Random sampling with the standard library finds
violations all the same, which is the done-criterion.
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
class PropertyFuzzOracle:
    """Random-sampling property fuzzer over the producer output."""

    llm: LlmClient
    sandbox: DockerSandbox
    name: str = "property_fuzz"
    weight: float = 1.0
    model: LlmModel = LlmModel.SONNET
    seed: int = 1234

    @property
    def protocol_description(self) -> str:
        return (
            "Writes a fuzz() function that random-samples many inputs and asserts the "
            "spec-guaranteed properties on each, run in the sealed sandbox; a single "
            "counterexample is a FAIL, so a tactic that works only on hand-picked inputs "
            "will be caught."
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
                "property-fuzz oracle needs source-code output; this target produced none",
                obligation_id,
            )

        fuzz_fn = await self._generate_fuzz(spec)
        if "def fuzz" not in fuzz_fn:
            return self._vote(
                VerdictDecision.UNAVAILABLE,
                "the model did not produce a fuzz() function to run",
                obligation_id,
            )

        checks = f"import random\nrandom.seed({self.seed})\n{fuzz_fn}\nfuzz()"
        result = await run_python_checks(self.sandbox, output.output, checks)
        if result.outcome is CheckOutcome.PASS:
            return self._vote(
                VerdictDecision.PASS,
                "property fuzzing found no violating input over the random trials",
                obligation_id,
            )
        if result.outcome is CheckOutcome.FAIL:
            return self._vote(
                VerdictDecision.FAIL,
                f"property fuzzing found a violating input: {result.detail[:200]}",
                obligation_id,
            )
        return self._vote(
            VerdictDecision.UNAVAILABLE,
            f"fuzz harness errored, inconclusive: {result.detail[:200]}",
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

    async def _generate_fuzz(self, spec: SealedSpec) -> str:
        obligations = "\n".join(f"- {o.id}: {o.description}" for o in spec.obligations)
        invariants = "\n".join(f"- {i.id}: {i.description}" for i in spec.invariants)
        prompt = (
            "A Python implementation of the specification below is defined above "
            "your code. Write a single function `def fuzz():` that property-fuzzes "
            "it. Inside, use the `random` module (already imported) to sample at "
            "least 200 random inputs and `assert` properties the specification "
            "guarantees. Assert only properties that MUST hold; include the "
            "offending inputs in each assert message. Output ONLY the function "
            "definition: no imports, no markdown, no explanation.\n\n"
            f"Obligations:\n{obligations}\n\nInvariants:\n{invariants}\n"
        )
        result = await self.llm.call(prompt, model=self.model)
        return extract_python_source(result.text)

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
