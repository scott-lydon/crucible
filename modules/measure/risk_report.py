"""SR 11-7 model risk report, rendered from a run's REAL persisted numbers.

Renders the six SR 11-7 sections (Purpose, Model description, Developmental
evidence, Ongoing monitoring, Limitations, Governance) as Markdown for a given
run. EVERY numeric field carries a traceable source-row reference in square
brackets (e.g. ``0.83 [run:<id>]`` / ``[white_box_metrics:<id>]`` /
``[blue_round:<id>]`` / ``[verdict:<id>]``) so a reader can jump to the source
row in Postgres (US-12 "click the number, jump to the source").

Honesty: a number that has not been measured renders the literal text
``Not yet measured`` (never 0.0). Pulls only from persisted rows — no LLM.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from modules.measure.metrics import catch_rate_for_run, compute_run_metrics
from shared.persistence import repo
from shared.persistence.models import RunRow

NOT_MEASURED = "Not yet measured"


@dataclass(frozen=True, slots=True)
class _Field:
    """A rendered numeric field plus the row id it traces to."""

    text: str  # the rendered "<value> [row:<id>]" or "Not yet measured"
    ref: str | None  # the bracketed reference, e.g. "[run:abc]" (None if unmeasured)


def _ref(kind: str, row_id: str) -> str:
    return f"[{kind}:{row_id}]"


def _num(value: float | None, kind: str, row_id: str | None) -> _Field:
    """Render a numeric field with its source-row reference, or the empty state.

    A ``None`` value (genuinely unmeasured) renders ``Not yet measured`` with no
    reference — never a fabricated 0.0.
    """
    if value is None or row_id is None:
        return _Field(text=NOT_MEASURED, ref=None)
    ref = _ref(kind, row_id)
    return _Field(text=f"{value:.4f} {ref}", ref=ref)


def _count(value: int, kind: str, row_id: str) -> _Field:
    ref = _ref(kind, row_id)
    return _Field(text=f"{value} {ref}", ref=ref)


async def render_risk_report(s: AsyncSession, run_id: str) -> str | None:
    """Render the SR 11-7 Markdown report for ``run_id`` (``None`` if no run row).

    Returns ``None`` when the run does not exist (the API renders a 404). For a
    real run with no measured numbers yet, the report still renders — every
    numeric field shows ``Not yet measured``.
    """
    run = await repo.get_run(s, run_id)
    if run is None:
        return None

    metrics = await compute_run_metrics(s, run_id)
    catch_rate = await catch_rate_for_run(s, run_id)
    wb = await repo.white_box_metrics_for_run(s, run_id)
    blue = await repo.blue_round_for_run(s, run_id)
    attacks = await repo.attacks_for_run(s, run_id)
    verdicts = await repo.verdicts_for_run(s, run_id)

    successful = [a for a in attacks if a.evaded and a.true_label_preserved]
    flagged = [v for v in verdicts if not v.aggregate_pass]

    # --- traceable fields ---
    catch = _num(catch_rate, "run", run_id)
    baseline = _num(
        metrics.baseline_validation_detection if metrics else None, "run", run_id
    )
    gap = _num(metrics.gap if metrics else None, "run", run_id)
    n_attacks = _count(len(attacks), "run", run_id)
    n_success = _count(len(successful), "run", run_id)
    n_verdicts = _count(len(verdicts), "run", run_id)
    n_flagged = _count(len(flagged), "run", run_id)

    bb = _num(wb.black_box_catch_rate if wb else None, "white_box_metrics",
              wb.run_id if wb else None)
    wbr = _num(wb.white_box_catch_rate if wb else None, "white_box_metrics",
               wb.run_id if wb else None)
    wb_gap = _num(wb.white_box_gap if wb else None, "white_box_metrics",
                  wb.run_id if wb else None)

    if blue is not None:
        det_before = _num(blue.detection_before, "blue_round", blue.id)
        det_after = _num(blue.detection_after, "blue_round", blue.id)
        recovered = _num(blue.recovered, "blue_round", blue.id)
        features = ", ".join(blue.features_added) if blue.features_added else "none"
    else:
        det_before = det_after = recovered = _Field(text=NOT_MEASURED, ref=None)
        features = NOT_MEASURED

    target = str((run.params_json or {}).get("target", "unknown"))

    return _assemble(
        run=run,
        target=target,
        catch=catch,
        baseline=baseline,
        gap=gap,
        n_attacks=n_attacks,
        n_success=n_success,
        n_verdicts=n_verdicts,
        n_flagged=n_flagged,
        bb=bb,
        wbr=wbr,
        wb_gap=wb_gap,
        det_before=det_before,
        det_after=det_after,
        recovered=recovered,
        features=features,
    )


def _assemble(
    *,
    run: RunRow,
    target: str,
    catch: _Field,
    baseline: _Field,
    gap: _Field,
    n_attacks: _Field,
    n_success: _Field,
    n_verdicts: _Field,
    n_flagged: _Field,
    bb: _Field,
    wbr: _Field,
    wb_gap: _Field,
    det_before: _Field,
    det_after: _Field,
    recovered: _Field,
    features: str,
) -> str:
    return f"""# SR 11-7 Model Risk Report — run `{run.id}`

> Source rows are referenced inline as `[table:id]`. Pillar: Measure.
> Status: {run.status} · Seed: `{run.seed}` · Rounds: {run.n_rounds} ·
> Threshold: {run.threshold} [run:{run.id}]

## 1. Purpose

This report documents the adversarial evaluation of the **{target}** fraud
detector under Crucible's red/blue/verify loop, for submission to internal model
risk committee review per Federal Reserve SR 11-7. The model under test is the
fraud detector; Crucible is the evaluation harness.

## 2. Model description

- Target: `{target}` [run:{run.id}]
- Rounds executed: {run.n_rounds} [run:{run.id}]
- Batch size: {run.batch_size} [run:{run.id}]
- Detector threshold: {run.threshold} [run:{run.id}]
- Adversarial attacks attempted: {n_attacks.text}
- Attacks that evaded AND preserved the true (fraud) label: {n_success.text}

## 3. Developmental evidence

- Baseline validation detection (round 0, validation slice): {baseline.text}
- Validation-vs-held-out detection gap: {gap.text}
- Oracle verdicts recorded: {n_verdicts.text}
- Verdicts the oracles FLAGGED (aggregate FAIL): {n_flagged.text}
- Platform catch rate (oracle-caught share of successful evasions): {catch.text}

## 4. Ongoing monitoring

- Black-box catch rate: {bb.text}
- White-box (informed-attacker) catch rate: {wbr.text}
- White-box gap (black − white; ≥ 0 on a sane run): {wb_gap.text}
- Blue recovery — detection before: {det_before.text}
- Blue recovery — detection after: {det_after.text}
- Blue recovery — recovered share: {recovered.text}
- Engineered feature(s) added by blue: {features}

## 5. Limitations

Fields rendered `{NOT_MEASURED}` above were not produced by this run and are NOT
substituted with zero. The catch rate is undefined (not zero) when no successful
evasion received an oracle verdict — for example an `n_rounds == 1` pass never
re-scores an evasion, so no decision is countable. The white-box gap is only
meaningful once the white-box self-test pass has run.

## 6. Governance

Crucible halts certification when white-box verifier recall falls below the
configured red line (default 0.70); new run launches are then refused with HTTP
409. This report is reproducible from the seed `{run.seed}` and the referenced
Postgres rows; every numeric field above carries its source-row identifier.
"""
