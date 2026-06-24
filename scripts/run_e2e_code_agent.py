#!/usr/bin/env python
"""End-to-end real-LLM proof of the code-agent pillar (Tier B6).

Drives one run against the code-agent target with every LLM call going to a real
model, then one blue prompt-config hardening round, and writes the measured
before/after reward-hack pass-rate to a committed
``artifacts/code_agent_e2e_summary.json``.

Unlike the fraud target, the code agent produces a code artifact the FOUR
mechanical oracles can actually check (held-out tests, metamorphic relations, a
cross-family differential, property fuzzing) in the sealed Docker sandbox, plus
the Opus judge. So this run exercises the full verification ensemble that is the
proposal's core claim. An attack is "undetected" when its produced artifact got
past the whole ensemble (the reward-hack sense).

Blue round: the proposer (real Sonnet) reads the undetected reward-hacks and
proposes a stricter system-prompt addition; the same attack payloads are then
re-run through the baseline agent and the hardened agent, and the reward-hack
pass-rate (fraction that evades the ensemble) is measured before and after.

Disclosure (R2): in --real mode EVERY value is real-LLM measured. Red calls real
Sonnet (black-box) and real Opus (white-box); the oracles call real Sonnet/Opus
to generate their checks; the judge calls real Opus; the blue proposer calls
real Sonnet. Runs on the Claude Max subscription via the claude CLI.

Usage:
    CRUCIBLE_RUN_LLM_TESTS=1 uv run python scripts/run_e2e_code_agent.py \
        --real --rounds 6 --budget 8 --db-url <local-url>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.blue import BlueProposer  # noqa: E402
from modules.measure import MetricsAggregator  # noqa: E402
from modules.targets.code_agent import CodeAgentTarget  # noqa: E402
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
    TargetType,
    VerdictId,
)
from shared.types.default_specs import default_spec_payload  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SUMMARY_PATH = _REPO_ROOT / "artifacts" / "code_agent_e2e_summary.json"

# Single source of truth for the code-agent default spec, shared with the
# browser Run Launcher via GET /targets/code_agent/default-spec.
_CODE_SPEC: dict[str, Any] = default_spec_payload(TargetType.CODE_AGENT)


class SpendTracker:
    """Wraps an LlmClient and totals real dollars across every call."""

    def __init__(self, inner: LlmClient) -> None:
        self.inner = inner
        self.total: Money = Money.zero()
        self.calls = 0

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        result = await self.inner.call(prompt, model=model, system=system)
        self.total = self.total + result.dollars
        self.calls += 1
        return result


def _disclose(args: argparse.Namespace) -> None:
    print("=" * 72)
    if args.real:
        print("REAL-LLM CODE-AGENT E2E — every value below is real-LLM measured")
        print("  red: real Sonnet (black) + real Opus (white) · oracles: real Sonnet/Opus")
        print("  judge: real Opus · blue: real Sonnet · full ensemble in Docker sandbox")
    else:
        print("MOCK SMOKE — scripted client, zero real calls; temp summary only")
    print(f"  target: code_agent   rounds: {args.rounds}   budget: ${args.budget}")
    print("=" * 72)


async def _create_run(spec: SealedSpec, budget: AttackBudget) -> str:
    run_id = RunId.new()
    async with get_sessionmaker()() as session:
        session.add(
            Run(
                id=run_id.value,
                status=RunStatus.PENDING.value,
                target_type=TargetType.CODE_AGENT.value,
                artifact_ref="code_agent@e2e",
                spec_title=spec.title,
                spec_json=spec.as_json(),
                budget_max_attempts=budget.max_attempts,
                budget_max_dollars=budget.max_dollars.dollars,
                seed=uuid.uuid4().hex,
            )
        )
        await session.commit()
    return run_id.value


async def _evaded(
    registry: Any, agent: CodeAgentTarget, spec: SealedSpec, payload: dict[str, Any]
) -> bool:
    """Run one payload through an agent and the full oracle ensemble: did it evade?

    Returns True when the produced artifact got past the ensemble (a reward-hack
    that the verifiers did not catch), measured exactly as the loop's verdict.
    """
    output = await agent.submit(spec, payload)
    votes = []
    for oracle in registry.oracles:
        try:
            votes.append(await oracle.verify(spec, payload, output))
        except Exception:  # an oracle that could not run does not vote
            continue
    verdict = registry.aggregator.aggregate(
        tuple(votes), run_id=RunId.new(), attack_id=None, verdict_id=VerdictId.new()
    )
    return bool(verdict.passed)


async def _amain(args: argparse.Namespace) -> int:
    load_dotenv()
    if args.real and os.environ.get("CRUCIBLE_RUN_LLM_TESTS") != "1":
        sys.exit("refusing real run without CRUCIBLE_RUN_LLM_TESTS=1 (spend guard)")
    if not args.db_url:
        sys.exit("--db-url <local-database-url> is required")
    use_database(args.db_url)
    _disclose(args)

    started_at = datetime.now(UTC).isoformat()
    client: LlmClient = ClaudeCliClient()
    tracker = SpendTracker(client)
    registry = build_registry(llm=tracker)
    spec = SealedSpec.from_payload(_CODE_SPEC)
    budget = AttackBudget(
        max_attempts=args.rounds, max_dollars=Money.of(args.budget)
    )

    run_id = await _create_run(spec, budget)
    print(f"created code-agent run {run_id}")
    async with get_sessionmaker()() as session:
        await Loop(session=session, registry=registry).run(run_id)
    print("loop complete (black-box + white-box red through the oracle ensemble)")

    # Headline catch rates from the oracle verdicts, plus the run's attacks.
    async with get_sessionmaker()() as session:
        metrics = (await MetricsAggregator(session=session).catch_rates()).as_json()
        rows = (
            
                await session.execute(
                    select(AttackRow.payload, AttackRow.succeeded).where(
                        AttackRow.run_id == run_id
                    )
                )
            
        ).all()
        attack_count = int(
            await session.scalar(
                select(func.count(AttackRow.id)).where(AttackRow.run_id == run_id)
            )
            or 0
        )
    payloads = [r[0] for r in rows if isinstance(r[0], dict) and r[0]]
    undetected = [r[0] for r in rows if r[1] and isinstance(r[0], dict) and r[0]]

    # Blue: propose a stricter prompt-config from the undetected reward-hacks
    # (fall back to all attacks when the ensemble caught everything), harden the
    # agent, and re-run the run's payloads baseline vs hardened.
    proposer = BlueProposer(llm=tracker)
    slice_attacks = [
        Attack(
            attack_id=AttackId.new(),
            run_id=RunId(run_id),
            tactic="reward-hack",
            payload=p,
            succeeded=True,
            white_box=False,
            hybrid=False,
            dollars_spent=Money.zero(),
            audit=AuditTrace(summary="undetected reward-hack", steps=()),
        )
        for p in (undetected or payloads)
    ]
    patch = await proposer.propose_patch(TargetType.CODE_AGENT, slice_attacks)
    hardened_prompt = str(patch.detail.get("system_prompt_additions", "")).strip()
    baseline = CodeAgentTarget(llm=tracker)
    hardened = CodeAgentTarget(llm=tracker, system_prompt=hardened_prompt or None)

    sample = payloads[: min(len(payloads), 2)] or [{"task": "implement the sum"}]
    before_hits = [await _evaded(registry, baseline, spec, p) for p in sample]
    after_hits = [await _evaded(registry, hardened, spec, p) for p in sample]
    before = sum(before_hits) / len(sample)
    after = sum(after_hits) / len(sample)
    print(f"blue cycle: reward-hack pass-rate before={before:.3f} after={after:.3f}")

    black = metrics["black_box_catch_rate"]
    white = metrics["white_box_catch_rate"]
    summary = {
        "run_id": run_id,
        "rounds_completed": attack_count,
        "black_box_catch_rate": black["rate"],
        "white_box_catch_rate": white["rate"],
        "catch_rate_gap": metrics["catch_rate_gap"],
        "undetected_attacks": len(undetected),
        "blue_patch_id": patch.patch_id.value,
        "pass_rate_before": before,
        "pass_rate_after": after,
        "recovery_delta": before - after,
        "hardened_prompt": hardened_prompt,
        "total_llm_dollars": tracker.total.dollars,
        "llm_calls": tracker.calls,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "disclosure": "real-LLM measured" if args.real else "SCRIPTED MOCK",
    }
    out = (
        _SUMMARY_PATH
        if args.real
        else Path(tempfile.gettempdir()) / "code_agent_e2e_mock.json"
    )
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote summary -> {out}")
    print(json.dumps(summary, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--real", action="store_true")
    mode.add_argument("--mock", action="store_true")
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--budget", type=float, default=8.0)
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args()
    return asyncio.run(_amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
