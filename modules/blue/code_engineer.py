"""Blue code-engineering agent (Option B) — a genuine maker, NOT a menu-picker.

The maker gets ONLY the raw data surface: the attack catalog (which feature the
adversary moved, in which direction, how often), the model's CURRENT base
features, the list of RAW column names, and a few SAMPLE raw rows so it sees the
data shape. NO derived-feature answer menu. From that it must REASON about what
signal the detector is missing and WRITE a feature-engineering transform — the
BODY of ``def engineer(row: dict) -> float`` over the raw columns.

The harness runs that untrusted body in the Docker sandbox, retrains, and
measures recovery. The maker is given the HISTORY of prior attempts this run
(rationale, the engineer_src tried, any sandbox error, and the recovery result)
so it forms a DIFFERENT hypothesis when a prior attempt did not recover. On a
sandbox error it may REPAIR (bounded by ``max_repairs``). It is ALLOWED TO FAIL:
there is no guaranteed-recovery fallback.

Model: real Opus 4.8 in the demo path (operator deviation from constitution §1,
which puts Sonnet on the inner blue loop — code generation is held to the higher
tier; see ``orchestrator/wiring.py``). Tests inject a deterministic mock provider
so the suite makes ZERO real LLM calls. Fails loud on malformed provider output.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from shared.llm.base import LLMProvider

_SYSTEM = (
    "You are a blue-team ML engineer hardening a fraud detector. The detector "
    "was trained on a NARROW set of base features and an adversary is evading it "
    "by moving those features. You do NOT get a menu of ready-made features. You "
    "get only the RAW data columns and must DISCOVER the missing signal yourself: "
    "reason about what the detector is blind to, then WRITE a Python feature-"
    "engineering transform that extracts that signal from the raw columns. Return "
    "the BODY of `def engineer(row: dict) -> float` (NOT the def line): given one "
    "raw row dict, compute a single numeric feature value. Use only the Python "
    "standard library. Form a hypothesis from the attack pattern and the raw "
    "schema; if prior attempts in the history did not recover detection, reason "
    "about WHY and try a DIFFERENT signal. If a prior attempt failed in the "
    "sandbox, fix the error."
)

_PROPOSAL_SCHEMA: Mapping[str, object] = {
    "type": "object",
    "properties": {
        "feature_name": {"type": "string"},
        "rationale": {"type": "string"},
        "engineer_src": {"type": "string"},
    },
    "required": ["feature_name", "rationale", "engineer_src"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class EngineeredProposal:
    """The maker's structured proposal: a named engineered feature + its code."""

    feature_name: str
    rationale: str
    engineer_src: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """One prior attempt this run, fed back so the maker can reason from it."""

    rationale: str
    feature_name: str
    engineer_src: str
    sandbox_error: str | None
    detection_after: float | None
    recovered: float | None


class BlueCodeEngineer:
    """Reasons from raw data to a feature-engineering transform. Allowed to fail."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_iters: int = 3,
        max_repairs: int = 1,
    ) -> None:
        self._provider = provider
        self.max_iters = max_iters
        self.max_repairs = max_repairs
        self._calls_made = 0

    @property
    def calls_made(self) -> int:
        return self._calls_made

    def propose(
        self,
        *,
        catalog_summary: Sequence[Mapping[str, object]],
        base_features: Sequence[str],
        raw_columns: Sequence[str],
        sample_rows: Sequence[Mapping[str, object]],
        history: Sequence[AttemptRecord],
    ) -> EngineeredProposal:
        """Ask the maker for a transform, given the raw surface + attempt history.

        Fails loud on malformed provider output (no fabricated proposal).
        """
        self._calls_made += 1
        resp = self._provider.complete(
            self._build_prompt(
                catalog_summary, base_features, raw_columns, sample_rows, history
            ),
            system=_SYSTEM,
            max_tokens=1024,
            json_schema=_PROPOSAL_SCHEMA,
        )
        parsed = json.loads(resp.text)  # fail loud on malformed provider output
        try:
            feature_name = str(parsed["feature_name"]).strip()
            rationale = str(parsed["rationale"]).strip()
            engineer_src = str(parsed["engineer_src"])
        except (KeyError, TypeError) as exc:
            raise ValueError(
                f"BlueCodeEngineer: provider returned malformed proposal: {parsed!r}"
            ) from exc
        if not engineer_src.strip():
            raise ValueError("BlueCodeEngineer: provider returned empty engineer_src.")
        return EngineeredProposal(
            feature_name=feature_name or "engineered",
            rationale=rationale,
            engineer_src=engineer_src,
        )

    @staticmethod
    def _build_prompt(
        catalog_summary: Sequence[Mapping[str, object]],
        base_features: Sequence[str],
        raw_columns: Sequence[str],
        sample_rows: Sequence[Mapping[str, object]],
        history: Sequence[AttemptRecord],
    ) -> str:
        history_block = (
            json.dumps(
                [
                    {
                        "rationale": a.rationale,
                        "feature_name": a.feature_name,
                        "engineer_src": a.engineer_src,
                        "sandbox_error": a.sandbox_error,
                        "detection_after": a.detection_after,
                        "recovered": a.recovered,
                    }
                    for a in history
                ],
                indent=2,
                default=str,
            )
            if history
            else "(none yet — this is the first attempt)"
        )
        return (
            "Successful evasions recorded by the red loop "
            "(feature moved, direction, source, count):\n"
            f"{json.dumps(list(catalog_summary), indent=2, default=str)}\n\n"
            f"Detector's CURRENT base features (already used): {list(base_features)}\n"
            f"RAW columns available on each row: {list(raw_columns)}\n\n"
            "A few SAMPLE raw rows (the data shape you must reason over):\n"
            f"{json.dumps([dict(r) for r in sample_rows], indent=2, default=str)}\n\n"
            "History of prior attempts THIS run (learn from what did NOT recover):\n"
            f"{history_block}\n\n"
            "Reason about what signal the detector is missing given the attack "
            "pattern and the raw schema, then return a structured proposal: a "
            "`feature_name`, a one-sentence `rationale`, and `engineer_src` — the "
            "BODY of `def engineer(row: dict) -> float` computing that feature "
            "from the raw columns of one row. Do NOT include the def line."
        )
