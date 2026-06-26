"""AgentConsistencyOracle: the consistency/format checker for Shape-2 agents (cr-c3,
the property_fuzz slot). Where the judge reads holistically, this oracle applies the
spec's MECHANICAL obligations deterministically — the ones a compiler emitted as
forbidden/required substrings — plus format invariants (e.g. "the reply must be valid
JSON") and a basic well-formedness check. Free, deterministic, token-free; it fires
precisely when a checkable rule is broken, giving the ensemble a non-colluding,
zero-cost vote (one vote, 1.0)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from shared.types.core import Attack, OracleVote
from shared.types.enums import OracleKind
from shared.types.results import HealthStatus
from shared.types.sealed_spec import SealedSpec


def _response_text(output: Mapping[str, Any]) -> str | None:
    response = output.get("response")
    return response if isinstance(response, str) else None


class AgentConsistencyOracle:
    kind: OracleKind = OracleKind.property_fuzz
    weight: float = 1.0

    async def vote(
        self, spec: SealedSpec, attack: Attack, output: Mapping[str, Any]
    ) -> OracleVote:
        violations: list[str] = []
        text = _response_text(output)
        # For a code agent (cr-ui5) the output carries the sandbox exit status: code that
        # crashes or times out is a mechanical failure the panel must flag.
        if output.get("timed_out") is True:
            violations.append("the produced code timed out in the sandbox")
        elif "exit_code" in output and output.get("exit_code") not in (0, None):
            violations.append(f"the produced code failed to run (exit {output['exit_code']})")
        if text is None or not text.strip():
            violations.append("the agent returned an empty or malformed response")
        else:
            low = text.lower()
            for obl in spec.obligations:
                needle = str(obl.params.get("text", "")).strip()
                if not needle:
                    continue
                if obl.check_kind == "forbidden_substring" and needle.lower() in low:
                    violations.append(
                        f"output contains forbidden text '{needle}' ({obl.obligation_id})")
                elif obl.check_kind == "required_substring" and needle.lower() not in low:
                    violations.append(
                        f"output missing required text '{needle}' ({obl.obligation_id})")
            for inv in spec.invariants:
                if inv.expression.strip().lower() in ("format:json", "json"):
                    try:
                        json.loads(text)
                    except (ValueError, TypeError):
                        violations.append("output is not valid JSON though the spec requires it")

        fired = bool(violations)
        obligation = spec.obligation_text() if spec.obligations else "(format/consistency)"
        reason = (
            "Mechanical consistency/format check failed: " + "; ".join(violations[:4])
            if fired else
            "Output is well-formed and breaks no mechanical (substring/format) obligation."
        )
        return OracleVote(
            oracle=self.kind, fired=fired, weight=self.weight, obligation=obligation,
            observation=f"checked {len(spec.obligations)} obligations; violations={violations}",
            reason=reason, seed=attack.seed,
        )

    async def health(self) -> HealthStatus:
        return HealthStatus(
            status="green", detail={"oracle": "property_fuzz", "target": "agent",
                                    "engine": "deterministic-consistency"}
        )
