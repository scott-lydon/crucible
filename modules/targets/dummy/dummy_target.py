"""DummyTarget: a deterministic, canned Target for the slice-1 loop smoke.

It satisfies `orchestrator.interfaces.Target` so the orchestrator can drive a
target end to end without a trained model or an LLM. Output is deterministic
(no randomness), so a replay produces byte-identical results. This is an
explicit test fixture target, not fabricated data presented as a real
measurement: it is the DUMMY target type and the wiring never selects it for
a real run.
"""

from __future__ import annotations

from typing import Any

from shared.types import (
    AuditStep,
    AuditTrace,
    ProbeResult,
    ProbeStatus,
    SealedSpec,
    TargetOutput,
    TargetType,
)


class DummyTarget:
    """A canned target whose output is a deterministic echo of its input."""

    target_type: TargetType = TargetType.DUMMY
    display_name: str = "Dummy"
    description: str = "Deterministic echo target used by the spine test."
    artifact_ref: str = "dummy@v0"
    # The spine test drives the oracle ensemble over this echo target, so its
    # verdict is the oracle ensemble's, like the code domain.
    oracle_verified: bool = True

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> TargetOutput:
        """Echo the input back under the spec's first obligation, with a score."""
        score = await self.query_target(attack_input)
        audit = AuditTrace(
            summary="dummy target produced a deterministic canned output",
            steps=(
                AuditStep(
                    label="echo",
                    detail={"input": attack_input, "score": score},
                ),
            ),
        )
        output = {"echo": attack_input, "checked_obligation": spec.obligations[0].id}
        return TargetOutput(output=output, score=score, audit=audit)

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        """A deterministic pseudo-score in [0, 1] derived from the input length.

        No randomness, so the score is reproducible for replay determinism.
        """
        return float(len(str(attack_input)) % 100) / 100.0

    async def self_test(self) -> ProbeResult:
        """Confirm the target responds to a probe; green when it returns a score."""
        score = await self.query_target({"probe": "ping"})
        return ProbeResult(
            status=ProbeStatus.GREEN,
            detail={"query_target": score, "note": "dummy target responding"},
        )
