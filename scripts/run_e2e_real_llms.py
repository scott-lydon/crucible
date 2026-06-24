#!/usr/bin/env python
"""End-to-end real-LLM proof of the three pillars (Tier A1).

Drives ONE run against the fraud target with every LLM call going to a real
model, then runs one blue-hardening round, and writes the measured headline
numbers to ``artifacts/e2e_run_summary.json``. Per the capstone proposal the
fraud detector is a SCORED target: the red agent's success is measured by the
model's own ``query_target`` score (attack-success-rate), not by the code
oracle ensemble (which verifies the code domain). The four oracles still run and
the Opus judge still votes, for the audit trail; the undetected signal for this
scored target is the model's own miss.

Disclosure (standing rule R2): in ``--real`` mode EVERY value in the summary is
measured from real LLM calls. Red search calls real Sonnet (black-box) and real
Opus (white-box); the LLM judge calls real Opus; the blue proposer calls real
Sonnet. The ``claude`` CLI runs on the operator's Claude Max subscription, so the
``total_cost_usd`` the CLI reports is the metered cost of the calls (covered by
the plan), summed here for transparency.

``--mock`` runs the identical pipeline with a scripted client (zero real calls)
to validate the plumbing; it writes to a temp file, never the committed artifact,
and labels every value as scripted, so a mock run can never be mistaken for the
real one.

Usage:
    # validate plumbing, no spend, against a local database
    uv run python scripts/run_e2e_real_llms.py --mock --db-url <local-url>

    # the real thing: drive the run, write to the production Postgres
    CRUCIBLE_RUN_LLM_TESTS=1 uv run python scripts/run_e2e_real_llms.py \
        --real --target fraud --rounds 48 --budget 25 \
        --db prod --api-base https://crucible-zaag.onrender.com
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import func, select

# Running as `python scripts/run_e2e_real_llms.py` puts scripts/ on sys.path, not
# the repo root; put the repo root first so the first-party packages resolve.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.blue import BlueProposer, BlueStore, fraud_scorer  # noqa: E402
from modules.blue.retrainer import DEFAULT_ARTIFACTS_DIR, DEFAULT_CSV_PATH  # noqa: E402
from modules.measure import MetricsAggregator  # noqa: E402
from orchestrator.loop import Loop  # noqa: E402
from orchestrator.wiring import build_registry  # noqa: E402
from shared.llm import ClaudeCliClient, LlmClient, LlmModel, LlmResult  # noqa: E402
from shared.persistence import get_sessionmaker, use_database  # noqa: E402
from shared.persistence.models import Attack as AttackRow  # noqa: E402
from shared.persistence.models import Run  # noqa: E402
from shared.types import (  # noqa: E402
    Attack,
    AttackBudget,
    AttackId,
    AuditTrace,
    Money,
    RunId,
    RunStatus,
    SealedSpec,
    TargetSpec,
    TargetType,
)
from shared.types.default_specs import default_spec_payload  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUMMARY_PATH = _REPO_ROOT / "artifacts" / "e2e_run_summary.json"
_V1_ARTIFACT = DEFAULT_ARTIFACTS_DIR / "fraud-v1.lgb"
_EVASION_THRESHOLD = 0.5

# Single source of truth for the fraud default spec, shared with the browser
# Run Launcher via GET /targets/fraud/default-spec.
_FRAUD_SPEC: dict[str, Any] = default_spec_payload(TargetType.FRAUD)


class SpendTracker:
    """Wraps an LlmClient and totals the real dollars across every call.

    Delegates to the inner client and accumulates ``total_cost_usd`` so the
    summary's ``total_llm_dollars`` covers red, oracle, and judge calls, not just
    the red proposals persisted on the attack rows. Structurally satisfies the
    LlmClient Protocol.
    """

    def __init__(self, inner: LlmClient) -> None:
        self.inner = inner
        self.total: Money = Money.zero()
        self.calls = 0
        self.by_model: dict[str, int] = {}

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        result = await self.inner.call(prompt, model=model, system=system)
        self.total = self.total + result.dollars
        self.calls += 1
        self.by_model[model.value] = self.by_model.get(model.value, 0) + 1
        return result


@dataclass(frozen=True, slots=True)
class PromptAwareMockClient:
    """A scripted client that returns a shape-appropriate JSON per prompt.

    The single response-per-model ScriptedLlmClient cannot serve both the
    white-box red proposal and the judge (both Opus); this inspects the prompt
    so the mock pipeline exercises every branch (red, judge, blue) end to end.
    Zero cost, flagged mock.
    """

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        lowered = prompt.lower()
        if '"decision"' in lowered or "independent judge" in lowered:
            text = '{"decision": "fail", "reason": "mock judge vote"}'
        elif "scale_pos_weight" in lowered:
            text = (
                '{"scale_pos_weight": 20, "n_estimators": 300, '
                '"learning_rate": 0.05, "reasoning": "mock blue config"}'
            )
        elif '"tactic"' in lowered or "red-team adversary" in lowered:
            text = (
                '{"tactic": "mock-evasion", "payload": {"Amount": 1.0, "V1": 0.5}, '
                '"reasoning": "mock evasion proposal"}'
            )
        else:
            text = "{}"
        return LlmResult(
            text=text,
            model=model,
            dollars=Money.zero(),
            tokens_in=0,
            tokens_out=0,
            session_id="mock",
            raw={"mock": True, "model": model.value},
        )


def _attack_from_payload(payload: dict[str, Any]) -> Attack:
    """An Attack value object wrapping one fraud payload for the blue cycle."""
    return Attack(
        attack_id=AttackId.new(),
        run_id=RunId.new(),
        tactic="missed-fraud",
        payload=payload,
        succeeded=True,
        white_box=False,
        hybrid=False,
        dollars_spent=Money.zero(),
        audit=AuditTrace(summary="real fraud the model missed", steps=()),
    )


async def _global_recall(
    artifact: Path, frauds: pd.DataFrame, features: list[str]
) -> float:
    """Recall over ALL real frauds: fraction scored at or above the threshold."""
    scorer = fraud_scorer(artifact)
    caught = 0
    for _, row in frauds.iterrows():
        payload = {f: float(row[f]) for f in features}
        if await scorer(payload) >= _EVASION_THRESHOLD:
            caught += 1
    return caught / len(frauds)


async def _missed_frauds(
    artifact: Path, frauds: pd.DataFrame, features: list[str]
) -> list[dict[str, Any]]:
    """Every real fraud the v1 model scores below the threshold (false negatives)."""
    scorer = fraud_scorer(artifact)
    missed: list[dict[str, Any]] = []
    for _, row in frauds.iterrows():
        payload = {f: float(row[f]) for f in features}
        if await scorer(payload) < _EVASION_THRESHOLD:
            missed.append(payload)
    return missed


async def _create_run_via_http(api_base: str, body: dict[str, Any]) -> str:
    """POST /runs against the deployed Crucible so the run originates there."""
    import httpx

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{api_base.rstrip('/')}/runs", json=body)
        resp.raise_for_status()
        return str(resp.json()["run_id"])


async def _create_run_direct(body: dict[str, Any]) -> str:
    """Insert a PENDING run row directly (mirrors POST /runs) into the bound DB."""
    spec = SealedSpec.from_payload(body["spec"])
    target = TargetSpec(
        target_type=TargetType(body["target_type"]), artifact_ref=body["artifact_ref"]
    )
    budget = AttackBudget(
        max_attempts=int(body["budget"]["max_attempts"]),
        max_dollars=Money.of(float(body["budget"]["max_dollars"])),
    )
    run_id = RunId.new()
    async with get_sessionmaker()() as session:
        session.add(
            Run(
                id=run_id.value,
                status=RunStatus.PENDING.value,
                target_type=target.target_type.value,
                artifact_ref=target.artifact_ref,
                spec_title=spec.title,
                spec_json=spec.as_json(),
                budget_max_attempts=budget.max_attempts,
                budget_max_dollars=budget.max_dollars.dollars,
                seed=uuid.uuid4().hex,
            )
        )
        await session.commit()
    return run_id.value


@dataclass(frozen=True, slots=True)
class BlueOutcome:
    patch_id: str
    v1_global_recall: float
    v2_global_recall: float
    detection_before: float
    detection_after: float
    artifact_ref: str


async def _run_blue_cycle(
    proposer: BlueProposer, run_id: str
) -> BlueOutcome:
    """One real blue-hardening round: harden on missed frauds, measure recovery.

    Pillar 3: the missed transactions (real frauds the v1 model scores as
    legitimate, plus this run's undetected red evasions) become adversarial
    training samples. A DISJOINT held-out set of missed frauds validates the
    patch (the contamination guard refuses overlap). v2 is retrained and its
    recall is measured against ALL real frauds.
    """
    frame = pd.read_csv(DEFAULT_CSV_PATH)
    features = [c for c in frame.columns if c != "Class"]
    frauds = frame[frame["Class"] == 1]

    v1_recall = await _global_recall(_V1_ARTIFACT, frauds, features)
    missed = await _missed_frauds(_V1_ARTIFACT, frauds, features)
    if len(missed) < 20:
        raise RuntimeError(
            f"need missed frauds to harden against; only {len(missed)} found"
        )

    # This run's undetected red evasions (real-LLM discovered), folded into the
    # patch's training samples and provenance so blue traces back to the run.
    async with get_sessionmaker()() as session:
        rows = (
            (
                await session.execute(
                    select(AttackRow.payload).where(
                        AttackRow.run_id == run_id, AttackRow.succeeded.is_(True)
                    )
                )
            )
            .scalars()
            .all()
        )
    run_evasions = [r for r in rows if isinstance(r, dict) and r]

    split = len(missed) * 7 // 10
    train_missed = missed[:split]
    holdout_missed = missed[split:]
    catalog_slice = [_attack_from_payload(p) for p in run_evasions + train_missed]
    holdout_attacks = [_attack_from_payload(p) for p in holdout_missed]

    patch = await proposer.propose_patch(TargetType.FRAUD, catalog_slice)
    validation = await proposer.validate_on_holdout(patch, holdout_attacks)
    artifact_path = Path(validation["artifact_ref"])
    v2_recall = await _global_recall(artifact_path, frauds, features)

    async with get_sessionmaker()() as session:
        store = BlueStore(session)
        await store.save_patch(patch)
        await store.save_holdout_run(patch, validation)
        await store.save_model_version(
            patch,
            version=int(validation["version"]),
            kind="retrain",
            artifact_ref=str(artifact_path),
            metrics={
                "auc": validation.get("auc"),
                "v1_global_recall": v1_recall,
                "v2_global_recall": v2_recall,
                "detection_before": validation["detection_before"],
                "detection_after": validation["detection_after"],
                "run_id": run_id,
            },
        )
        await session.commit()

    return BlueOutcome(
        patch_id=patch.patch_id.value,
        v1_global_recall=v1_recall,
        v2_global_recall=v2_recall,
        detection_before=float(validation["detection_before"]),
        detection_after=float(validation["detection_after"]),
        artifact_ref=str(artifact_path),
    )


def _clean_stale_v2_plus() -> None:
    """Remove any fraud-v2+.lgb so the blue retrain writes exactly fraud-v2.lgb."""
    for path in DEFAULT_ARTIFACTS_DIR.glob("fraud-v*.lgb"):
        if path.name != "fraud-v1.lgb":
            path.unlink()
            path.with_suffix(".meta.json").unlink(missing_ok=True)


def _bind_database(args: argparse.Namespace) -> str:
    """Point the persistence engine at the chosen database, return a label."""
    if args.db == "prod":
        url = os.environ.get("CRUCIBLE_PROD_DATABASE_URL")
        if not url:
            sys.exit(
                "CRUCIBLE_PROD_DATABASE_URL is not set. Put the production "
                "external connection string in the gitignored .env."
            )
        use_database(url, connect_args={"ssl": "require"})
        return "production Postgres (external, SSL)"
    if not args.db_url:
        sys.exit("--db local requires --db-url <local-database-url>")
    use_database(args.db_url)
    return f"local Postgres ({args.db_url.rsplit('@', 1)[-1]})"


def _disclose(args: argparse.Namespace, db_label: str) -> None:
    print("=" * 72)
    if args.real:
        print("REAL-LLM END-TO-END RUN — every value below is real-LLM measured")
        print("  red:   real Sonnet (black-box) + real Opus (white-box)")
        print("  judge: real Opus      blue: real Sonnet")
        print("  cost:  charged to the Claude Max subscription via the claude CLI")
    else:
        print("MOCK SMOKE — ALL LLM CALLS ARE SCRIPTED (zero real calls)")
        print("  every value is scripted; summary is written to a TEMP file,")
        print("  never the committed artifacts/e2e_run_summary.json")
    print(f"  target: {args.target}   rounds: {args.rounds}   budget: ${args.budget}")
    print(f"  database: {db_label}")
    print("=" * 72)


async def _amain(args: argparse.Namespace) -> int:
    load_dotenv()
    if args.real and not args.mock and os.environ.get("CRUCIBLE_RUN_LLM_TESTS") != "1":
        sys.exit("refusing real run without CRUCIBLE_RUN_LLM_TESTS=1 (spend guard)")

    db_label = _bind_database(args)
    _disclose(args, db_label)

    started_at = datetime.now(UTC).isoformat()
    client: LlmClient = ClaudeCliClient() if args.real else PromptAwareMockClient()
    tracker = SpendTracker(client)
    registry = build_registry(llm=tracker)

    run_body = {
        "target_type": args.target,
        "artifact_ref": "fraud-v1",
        "spec": _FRAUD_SPEC,
        "budget": {"max_attempts": args.rounds, "max_dollars": args.budget},
    }
    if args.api_base:
        run_id = await _create_run_via_http(args.api_base, run_body)
        print(f"created run via POST {args.api_base}/runs -> {run_id}")
    else:
        run_id = await _create_run_direct(run_body)
        print(f"created run (direct insert) -> {run_id}")

    async with get_sessionmaker()() as session:
        await Loop(session=session, registry=registry).run(run_id)
    print("loop complete (black-box + white-box red passes persisted)")

    _clean_stale_v2_plus()
    proposer = BlueProposer(llm=tracker, base_fraud_artifact=_V1_ARTIFACT)
    blue = await _run_blue_cycle(proposer, run_id)
    print(
        f"blue cycle complete: v1_recall={blue.v1_global_recall:.4f} "
        f"v2_recall={blue.v2_global_recall:.4f} patch={blue.patch_id}"
    )

    async with get_sessionmaker()() as session:
        metrics = (await MetricsAggregator(session=session).catch_rates()).as_json()
        attack_count = int(
            await session.scalar(
                select(func.count(AttackRow.id)).where(AttackRow.run_id == run_id)
            )
            or 0
        )

    black = metrics["black_box_catch_rate"]
    white = metrics["white_box_catch_rate"]
    undetected = int(black["undetected"]) + int(white["undetected"])
    summary = {
        "run_id": run_id,
        "rounds_completed": attack_count,
        "black_box_catch_rate": black["rate"],
        "white_box_catch_rate": white["rate"],
        "catch_rate_gap": metrics["catch_rate_gap"],
        "undetected_attacks": undetected,
        "blue_patch_id": blue.patch_id,
        "v1_global_recall": blue.v1_global_recall,
        "v2_global_recall": blue.v2_global_recall,
        "recall_delta": blue.v2_global_recall - blue.v1_global_recall,
        "total_llm_dollars": tracker.total.dollars,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "disclosure": (
            "real-LLM measured" if args.real else "SCRIPTED MOCK — not a real run"
        ),
        "llm_calls": tracker.calls,
        "llm_calls_by_model": tracker.by_model,
    }

    out = _SUMMARY_PATH if args.real else Path(tempfile.gettempdir()) / "e2e_mock_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote summary -> {out}")
    print(json.dumps(summary, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--real", action="store_true", help="use real LLM calls")
    mode.add_argument("--mock", action="store_true", help="scripted client, no spend")
    parser.add_argument("--target", default="fraud", choices=["fraud"])
    parser.add_argument("--rounds", type=int, default=48)
    parser.add_argument("--budget", type=float, default=25.0)
    parser.add_argument("--db", choices=["prod", "local"], default="local")
    parser.add_argument("--db-url", default=None, help="explicit local database URL")
    parser.add_argument(
        "--api-base", default=None, help="POST /runs here to create the run (deployed URL)"
    )
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
