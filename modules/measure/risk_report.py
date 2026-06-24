"""SR 11-7 model risk report from real run state (US-12).

Renders the six SR 11-7 sections (purpose, model description, developmental
evidence, ongoing monitoring, limitations, governance) from one run's actual
rows. Every numeric field is a Markdown link to the API route that returns its
source row, so clicking a number jumps to the Postgres row it came from; no
number is typed in by hand or sampled. The same text renders to a submittable
PDF (modules/measure/pdf.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.pdf import text_to_pdf
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import BluePatch as BluePatchRow
from shared.persistence.models import HoldoutRun, Run
from shared.persistence.models import Verdict as VerdictRow

_HALT_THRESHOLD = 0.7


class ReportRunNotFoundError(Exception):
    """The report was requested for a run id that does not exist."""


def _link(value: Any, route: str) -> str:
    """A Markdown link from a numeric value to the route that returns its row."""
    return f"[{value}]({route})"


def _rate(caught: int, judged: int) -> float | None:
    return (caught / judged) if judged else None


def _pct(x: float | None) -> str:
    return "not yet measured" if x is None else f"{x * 100:.1f}%"


@dataclass(frozen=True, slots=True)
class RiskReport:
    """Builds the SR 11-7 report for one run over a database session."""

    session: AsyncSession

    async def render_markdown(self, run_id: str) -> str:
        run = await self.session.get(Run, run_id)
        if run is None:
            raise ReportRunNotFoundError(f"no run {run_id!r}")
        attacks = (
            (await self.session.execute(select(AttackRow).where(AttackRow.run_id == run_id)))
            .scalars()
            .all()
        )
        verdicts = (
            (await self.session.execute(select(VerdictRow).where(VerdictRow.run_id == run_id)))
            .scalars()
            .all()
        )
        verdict_by_attack = {v.attack_id: v for v in verdicts}
        patch = (
            await self.session.execute(
                select(BluePatchRow)
                .where(BluePatchRow.target_type == run.target_type)
                .order_by(BluePatchRow.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        # Per-run catch rate per box, from this run's judged attacks.
        judged = {False: [0, 0], True: [0, 0]}  # box -> [judged, caught]
        for a in attacks:
            v = verdict_by_attack.get(a.id)
            if v is None:
                continue
            judged[a.white_box][0] += 1
            if not v.passed:
                judged[a.white_box][1] += 1
        black = _rate(judged[False][1], judged[False][0])
        white = _rate(judged[True][1], judged[True][0])
        gap = (black - white) if black is not None and white is not None else None
        successful = sum(1 for a in attacks if a.succeeded)
        asr = _rate(successful, len(verdicts)) if verdicts else None

        run_route = f"/runs/{run_id}"
        sections = [
            "# SR 11-7 Model Risk Report",
            f"_Run {_link(run_id, run_route)} · target `{run.target_type}` · "
            f"status `{run.status}`_",
            "",
            "## 1. Purpose",
            "This report documents an adversarial-robustness evaluation of the model "
            "under test, produced by Crucible for internal model risk committee review. "
            "Crucible certifies nothing; it reports a catch rate against an informed "
            "(white-box) adversary and the evidence behind it.",
            "",
            "## 2. Model description",
            f"- Target type: `{run.target_type}`",
            f"- Artifact under test: `{run.artifact_ref}`",
            f"- Specification: {run.spec_title}",
            f"- Run seed (replay key): `{run.seed}`",
            "",
            "## 3. Developmental evidence",
            f"- Adversarial attempts driven: {_link(len(attacks), run_route)}",
            f"- Verdicts recorded: {_link(len(verdicts), run_route)}",
            f"- Black-box verifier recall: {_link(_pct(black), run_route)} "
            f"({judged[False][1]}/{judged[False][0]} caught)",
            f"- White-box verifier recall: {_link(_pct(white), run_route)} "
            f"({judged[True][1]}/{judged[True][0]} caught)",
            "",
            "Per-verdict evidence (each links to its source row):",
        ]
        for v in verdicts:
            route = f"/runs/{run_id}/verdicts/{v.id}"
            outcome = "passed (undetected)" if v.passed else "caught"
            sections.append(f"- Verdict {_link(v.id[:8], route)}: tally "
                            f"{_link(v.tally, route)}, {outcome}")

        sections += [
            "",
            "## 4. Ongoing monitoring",
            f"- Attack-success-rate (undetected hacks / verdicts): "
            f"{_link(_pct(asr), run_route)}",
        ]
        if patch is not None:
            patch_route = f"/blue/{patch.id}"
            holdout = (
                await self.session.execute(
                    select(HoldoutRun).where(HoldoutRun.patch_id == patch.id).limit(1)
                )
            ).scalar_one_or_none()
            if holdout is not None:
                sections.append(
                    f"- Blue-loop hardening {_link('patch', patch_route)}: detection "
                    f"{_link(_pct(holdout.detection_before), patch_route)} → "
                    f"{_link(_pct(holdout.detection_after), patch_route)} on held-out "
                    f"attacks (recovered: {holdout.recovered})"
                )
            else:
                sections.append(f"- Blue-loop {_link('patch proposed', patch_route)}, "
                                "held-out validation pending")
        else:
            sections.append("- No blue-loop patch recorded for this target yet")

        sections += [
            "",
            "## 5. Limitations",
            f"- Catch-rate gap (black-box minus white-box): {_pct(gap)}. A large gap "
            "would mean the verifier relies on the attacker's ignorance.",
            f"- Certification halts when white-box recall falls below {_HALT_THRESHOLD:.2f} "
            "(the configured red line).",
            "- The spec is a proxy for intent; recall is reported continuously rather "
            "than asserting correctness.",
            "",
            "## 6. Governance",
            f"- Run of record: {_link(run_id, run_route)}",
            f"- Seed for byte-exact replay: `{run.seed}`",
            "- Every number above links to the Postgres row it was computed from; the "
            "audit traces are reachable from each verdict row.",
            "",
        ]
        return "\n".join(sections)

    async def render_pdf(self, run_id: str) -> bytes:
        """The same report content as a submittable PDF (US-12)."""
        return text_to_pdf(await self.render_markdown(run_id))
