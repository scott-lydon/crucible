"""SR 11-7 model risk report (spec US-12), rendered from a run's real persisted numbers —
never a template with sample values (constitution.md section 5). Target-agnostic: the same
six-section structure covers the fraud model and any agent. The headline is the trust score
(cr-f1); a co-evolution summary is included when the run hardened the agent (cr-f2). Also
renders to PDF for committee distribution."""

from __future__ import annotations

import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import compute_metrics
from modules.measure.trust import compute_trust
from shared.persistence.models import Run
from shared.persistence.store import coevolution_series


def _pct(value: float | None) -> str:
    return "Not yet measured" if value is None else f"{value * 100:.1f}%"


def _usd(value: float | None) -> str:
    return "Not yet measured" if value is None else f"${value:.4f}"


def _ensemble(target_kind: str) -> str:
    if target_kind == "fraud":
        return ("held-out (sealed data partition = ground truth), differential "
                "(IsolationForest), metamorphic, property-fuzz, LLM judge (half vote); "
                "catch threshold 2.0.")
    return ("held-out (hidden checks generated from the spec = ground truth), differential "
            "(an independent reference model), metamorphic (paraphrase stability), "
            "consistency/format, LLM judge (half vote); catch threshold 2.0.")


async def sr_11_7_markdown(session: AsyncSession, run_id: str) -> str:
    run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if run is None:
        raise KeyError(f"run {run_id} not found")
    m = await compute_metrics(session, run_id)
    trust = await compute_trust(session, run_id)
    tiles = m["tiles"]
    detail = m["detail"]
    bb = detail["black_box"]
    wb = detail["white_box"]

    trust_line = (
        "Not yet measured" if trust["trust_score"] is None
        else f"**{trust['trust_score']}/100** (band {trust['band']}) — "
             f"{trust['silent_failures']} silent failure(s) over {trust['n_attacks']} "
             f"{str(trust['basis']).replace('_', '-')} attacks")

    coevo = await coevolution_series(session, run_id)
    coevo_section = ""
    if coevo:
        rows = "\n".join(
            f"- Round {r.round_index}: agent v{r.config_version} · ASR "
            f"{r.asr * 100:.0f}% · detection {r.detection * 100:.0f}%"
            f" · blue safe-rate {(_pct(r.safe_before))}→{_pct(r.safe_after)}"
            for r in coevo
        )
        coevo_section = (
            "\n## 3b. Co-evolution (red → verify → blue)\n"
            "The AI defender rewrote the agent's system prompt each round (vendor model "
            "never retrained); ASR is the agent's residual failure rate per round:\n"
            f"{rows}\n"
        )

    return f"""# SR 11-7 Model Risk Report — run `{run_id}`

## 0. Headline — Trust score
{trust_line}

Trust = 1 - (held-out-confirmed failures that slipped the panel / attacks). It is a
measured FLOOR on trust, not a certification. Caveats:
{chr(10).join('- ' + c for c in trust['caveats'])}

## 1. Purpose
Independent verification of the **{run.target_kind}** AI system ({run.shape}) under
Crucible's adversarial red-and-blue protocol. This report supports model risk
committee review per United States Federal Reserve Supervisory Letter 11-7.

## 2. Model description
- Target: `{run.target_kind}` (Shape: `{run.shape}`)
- Budget: {run.budget_rounds} rounds, ${run.budget_dollars} ceiling
- Verification ensemble: {_ensemble(run.target_kind)}

## 3. Developmental evidence
- Verdicts examined: **{m['verdicts']}** (source: `verdicts` rows for this run)
- Producer wrongness (held-out ground truth fired): **{detail['producer_wrong_total']}**
- Ensemble catches: **{detail['caught_total']}**
- Black-box catch rate: **{_pct(tiles['black_box_catch_rate'])}**
  ({bb['caught']}/{bb['producer_wrong']})
- White-box catch rate (attacker knows the scheme): **{_pct(tiles['white_box_catch_rate'])}**
  ({wb['caught']}/{wb['producer_wrong']})
- Black-box vs white-box gap: **{_pct(tiles['validation_vs_holdout_gap'])}**
{coevo_section}
## 4. Ongoing monitoring
- Undetected-hack rate: **{_pct(tiles['undetected_hack_rate'])}** — the residual an
  external auditor multiplies by real-world volume to estimate exposure.
- Cost per caught hack: **{_usd(tiles['dollars_per_caught_hack'])}**
  (total LLM spend ${detail['dollars_total']:.4f}).

## 5. Limitations
- The held-out oracle is the ground-truth grader; the reported catch rate is the
  recall of the *other* mechanisms confirming its findings.
- Open-ended agent tasks lack perfect ground truth, so the judge and held-out checks
  carry more weight there; the trust score is a floor, not a ceiling.
- A static catch rate reflects the current ensemble; unknown hack classes are not
  bounded. Crucible reports residuals; it does not certify the model.

## 6. Governance
- The certification authority is the consuming model risk committee, not Crucible.
- Certification halts automatically when white-box verifier recall drops below the
  configured red line (spec US-13).
"""


async def sr_11_7_pdf(session: AsyncSession, run_id: str) -> bytes:
    """The same report as a PDF for committee distribution (cr-f2). Renders the markdown
    line-by-line with simple heading styles — no external services, deterministic."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    markdown = await sr_11_7_markdown(session, run_id)
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=LETTER, topMargin=0.7 * inch,
                            bottomMargin=0.7 * inch)
    flow = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line:
            flow.append(Spacer(1, 6))
            continue
        text = line.replace("**", "").replace("`", "")
        if line.startswith("## "):
            flow.append(Paragraph(text[3:], styles["Heading2"]))
        elif line.startswith("# "):
            flow.append(Paragraph(text[2:], styles["Title"]))
        elif line.startswith("- "):
            flow.append(Paragraph("• " + text[2:], styles["Normal"]))
        else:
            flow.append(Paragraph(text, styles["Normal"]))
    doc.build(flow)
    return buf.getvalue()
