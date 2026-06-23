"""SR 11-7 model risk report (spec US-12), rendered from a run's real persisted
numbers — never a template with sample values (constitution.md section 5). Six
sections per the United States Federal Reserve Supervisory Letter 11-7 structure."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import compute_metrics
from shared.persistence.models import Run


def _pct(value: float | None) -> str:
    return "Not yet measured" if value is None else f"{value * 100:.1f}%"


def _usd(value: float | None) -> str:
    return "Not yet measured" if value is None else f"${value:.4f}"


async def sr_11_7_markdown(session: AsyncSession, run_id: str) -> str:
    run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one_or_none()
    if run is None:
        raise KeyError(f"run {run_id} not found")
    m = await compute_metrics(session, run_id)
    tiles = m["tiles"]
    detail = m["detail"]
    bb = detail["black_box"]
    wb = detail["white_box"]

    return f"""# SR 11-7 Model Risk Report — run `{run_id}`

## 1. Purpose
Independent verification of the **{run.target_kind}** AI system ({run.shape}) under
Crucible's adversarial red-and-blue protocol. This report supports model risk
committee review per United States Federal Reserve Supervisory Letter 11-7.

## 2. Model description
- Target: `{run.target_kind}` (Shape: `{run.shape}`)
- Budget: {run.budget_rounds} rounds, ${run.budget_dollars} ceiling
- Verification ensemble: held-out (ground truth), differential (IsolationForest),
  metamorphic, property-fuzz, LLM judge (half vote); catch threshold 2.0.

## 3. Developmental evidence
- Verdicts examined: **{m['verdicts']}** (source: `verdicts` rows for this run)
- Producer wrongness (held-out ground truth fired): **{detail['producer_wrong_total']}**
- Ensemble catches: **{detail['caught_total']}**
- Black-box catch rate: **{_pct(tiles['black_box_catch_rate'])}**
  ({bb['caught']}/{bb['producer_wrong']})
- White-box catch rate (attacker knows the scheme): **{_pct(tiles['white_box_catch_rate'])}**
  ({wb['caught']}/{wb['producer_wrong']})
- Black-box vs white-box gap: **{_pct(tiles['validation_vs_holdout_gap'])}**

## 4. Ongoing monitoring
- Undetected-hack rate: **{_pct(tiles['undetected_hack_rate'])}** — the residual an
  external auditor multiplies by real-world volume to estimate exposure.
- Cost per caught hack: **{_usd(tiles['dollars_per_caught_hack'])}**
  (total LLM spend ${detail['dollars_total']:.4f}).

## 5. Limitations
- The held-out oracle is the ground-truth grader; the reported catch rate is the
  recall of the *other* mechanisms confirming its findings.
- A static catch rate reflects the current ensemble; unknown hack classes are not
  bounded. Crucible reports residuals; it does not certify the model.

## 6. Governance
- The certification authority is the consuming model risk committee, not Crucible.
- Certification halts automatically when white-box verifier recall drops below the
  configured red line (spec US-13).
"""
