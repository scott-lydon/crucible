"""The orchestrator loop. Per constitution.md section 2, ``loop.py`` carries no
business logic: it calls interfaces in sequence and writes audit rows, emitting each
to the Measure sink.

Slice 1 lands the per-round red -> submit path against the dummy target. The verify
(oracles), harden (blue) and white-box passes slot into the same loop as their
slices land; the loop runs whatever pillars wiring has registered."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from modules.measure.budget import global_spend, run_spend, should_halt
from orchestrator.interfaces import (
    ConfigurableBlue,
    Oracle,
    Primable,
    RedAgent,
    Retargetable,
    SchemeAware,
    Target,
)
from orchestrator.wiring import Container
from shared.config import load_settings
from shared.llm import LLMCallRecord, drain_records, record_into, record_llm_call
from shared.persistence.db import session_scope
from shared.persistence.models import AttackRow, Run, SpecRow, VerdictRow
from shared.persistence.resolver import resolve_spec
from shared.persistence.store import (
    load_agent_config,
    save_agent_config,
    save_coevolution_round,
)
from shared.telemetry.log import get_logger
from shared.types.core import Attack, AttackBudget, TargetSpec, Verdict
from shared.types.enums import OracleKind, Pillar, RunStatus
from shared.types.ids import AttackId, RunId, new_id
from shared.types.results import ProducerResult
from shared.types.sealed_spec import HumanSpec, SealedSpec

_log = get_logger("orchestrator.loop")


async def create_run(
    target_spec: TargetSpec,
    sealed_spec: SealedSpec,
    budget: AttackBudget,
    *,
    source_text: HumanSpec | None = None,
    compiler: str = "deterministic",
) -> RunId:
    """Persist a new run and its sealed spec; return the run id. The full spec lives
    in the ``specs`` table, read by oracles through a server-side resolver the producer
    container cannot reach (constitution.md section 3).

    For a Shape-2 agent run, ``source_text`` is the operator's plain-English spec and
    ``compiler`` is how it was turned into obligations — persisted for spec history."""
    run_id = RunId(new_id("run"))
    async with session_scope() as session:
        session.add(
            Run(
                id=run_id,
                status=RunStatus.pending,
                target_kind=target_spec.target_kind,
                shape=target_spec.shape,
                budget_rounds=budget.max_rounds,
                budget_dollars=budget.max_dollars,
            )
        )
        session.add(
            SpecRow(
                id=new_id("spec"),
                run_id=run_id,
                target_kind=sealed_spec.target_kind,
                shape=sealed_spec.shape,
                holdout_generator_kind=sealed_spec.holdout_generator_kind,
                payload=sealed_spec.to_dict(),
                compiler=compiler,
                source_text=source_text.to_dict() if source_text is not None else None,
            )
        )
    _log.info("run_created", run_id=str(run_id), target=target_spec.target_kind)
    return run_id


async def _set_status(run_id: RunId, status: RunStatus, *, error: str | None = None) -> None:
    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status = status
        if error is not None:
            run.error = error


@dataclass(frozen=True, slots=True)
class _RunCtx:
    spec: SealedSpec
    target_kind: str
    budget_rounds: int
    budget_dollars: float
    agent_config_id: str | None
    target_http: dict[str, Any] | None


async def _load_context(run_id: RunId) -> _RunCtx:
    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        spec = await resolve_spec(session, run_id)
        return _RunCtx(
            spec, run.target_kind, run.budget_rounds, run.budget_dollars,
            run.agent_config_id, run.target_http)


class _BudgetHaltError(Exception):
    """Raised mid-run when a real-LLM budget cap is reached (cr-f4); caught to mark the
    run halted (not failed) so the spend stops cleanly."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


async def _enforce_budget(run_id: RunId, per_run_cap: float) -> None:
    """Update the run's dollar spend from llm_calls and raise _BudgetHaltError if the per-run or
    global cap is reached. A no-op in mock mode (every call costs $0)."""
    global_cap = load_settings().global_budget_dollars
    async with session_scope() as session:
        spent = await run_spend(session, str(run_id))
        total = await global_spend(session)
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.dollars_spent = spent
    reason = should_halt(spent, per_run_cap, total, global_cap)
    if reason is not None:
        raise _BudgetHaltError(reason)


def _retarget_oracles(oracles: list[Oracle], target: Target) -> None:
    """Point re-querying oracles (metamorphic) at the run's actual target so they grade
    the agent under test, not a default (cr-ui3). Shared oracle instances, so this is
    per-run state — fine for sequential runs."""
    for oracle in oracles:
        if isinstance(oracle, Retargetable):
            oracle.set_resubmit(target.submit)


async def _resolve_target(container: Container, ctx: _RunCtx) -> Target:
    """The target for a run: a BYO HTTP endpoint (cr-ui4) or a per-run agent config (BYO or
    demo, cr-e2) built through the matching factory, else the registered target."""
    if ctx.target_http is not None and container.http_target_factory is not None:
        return container.http_target_factory(ctx.target_http)
    if ctx.agent_config_id is not None and container.agent_target_factory is not None:
        async with session_scope() as session:
            config = await load_agent_config(session, ctx.agent_config_id)
        return container.agent_target_factory(config)
    return container.get_target(ctx.target_kind)


async def _persist_round(
    run_id: RunId, attack: Attack, result: ProducerResult, verdict: Verdict | None
) -> None:
    async with session_scope() as session:
        session.add(
            AttackRow(
                id=attack.attack_id,
                run_id=run_id,
                round_index=attack.round_index,
                tactic=attack.tactic,
                payload=dict(attack.payload),
                rationale=attack.rationale,
                white_box=attack.white_box,
                hybrid=attack.hybrid,
                # "succeeded" = evaded the oracle ensemble (verdict clean). Whether the
                # producer was truly wrong needs ground truth — set by Measure once the
                # held-out oracle lands (slice 5).
                succeeded=verdict is not None and not verdict.caught,
                pillar=Pillar.red,
                seed=attack.seed,
                dollars_spent=result.dollars,
                audit_trace={
                    "producer_output": dict(result.output),
                    "producer_summary": result.audit.summary,
                    "producer_detail": dict(result.audit.detail),
                },
            )
        )
        if verdict is not None:
            session.add(
                VerdictRow(
                    id=verdict.verdict_id,
                    run_id=run_id,
                    attack_id=attack.attack_id,
                    producer_output=dict(verdict.producer_output),
                    votes=[v.as_dict() for v in verdict.votes],
                    tally=verdict.tally,
                    threshold=verdict.threshold,
                    outcome=str(verdict.outcome),
                    pillar=Pillar.oracles,
                    seed=verdict.seed,
                    dollars_spent=verdict.dollars,
                    audit_trace={"summary": verdict.audit.summary, **verdict.audit.detail},
                )
            )


def _held_out_fired(verdict: Verdict) -> bool:
    return any(v.oracle is OracleKind.held_out and v.fired for v in verdict.votes)


async def _persist_llm_calls(
    run_id: RunId, attack_id: AttackId, records: list[LLMCallRecord]
) -> None:
    """Persist this round's LLM calls (cr-b4) so the Inspect button has its rows. Each is
    tagged with the run and the attack it belongs to (parent_action_id)."""
    if not records:
        return
    async with session_scope() as session:
        for rec in records:
            await record_llm_call(
                session, rec.result, system=rec.system, prompt=rec.prompt,
                pillar=rec.pillar, run_id=str(run_id), parent_action_id=str(attack_id),
            )


async def _run_round(
    container: Container, spec: SealedSpec, target: Target, red: RedAgent,
    oracles: list[Oracle], run_id: RunId, round_index: int, white_box: bool,
    last_verdict: Verdict | None,
) -> Verdict | None:
    sink = container.sink
    attack = await red.propose(spec, run_id, round_index, last_verdict, white_box=white_box)
    result = await target.submit(attack.payload)
    verdict = await container.verify(oracles, spec, attack, result.output) if oracles else None
    await _persist_round(run_id, attack, result, verdict)
    # Persist every LLM call this round made (red + target + oracles) for the Inspect
    # button (cr-b4); the recorder buffers them task-locally during the round.
    await _persist_llm_calls(run_id, attack.attack_id, drain_records())
    await sink.emit(run_id, "attack", {
        "attack_id": str(attack.attack_id), "round": round_index,
        "tactic": attack.tactic, "white_box": white_box, "payload": dict(attack.payload),
    })
    await sink.emit(run_id, "producer_output",
                    {"attack_id": str(attack.attack_id), "output": dict(result.output)})
    if verdict is not None:
        await sink.emit(run_id, "verdict", {
            "verdict_id": str(verdict.verdict_id), "attack_id": str(attack.attack_id),
            "white_box": white_box, "outcome": str(verdict.outcome), "tally": verdict.tally,
            "threshold": verdict.threshold, "summary": verdict.audit.summary,
        })
    return verdict


async def _set_white_box_recall(run_id: RunId, recall: float) -> None:
    async with session_scope() as session:
        run = (await session.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.white_box_recall = recall


async def run_loop(run_id: RunId, container: Container) -> None:
    """Drive one run: a black-box red pass, then the white-box self-test pass where the
    same red agent is told the verification scheme (spec US-14, constitution section 3).
    Exceptions are not swallowed; on failure the run is marked failed and re-raised."""
    sink = container.sink
    await _set_status(run_id, RunStatus.running)
    await sink.emit(run_id, "run_started", {"run_id": str(run_id)})
    try:
        ctx = await _load_context(run_id)
        spec, target_kind, budget_rounds, budget_dollars = (
            ctx.spec, ctx.target_kind, ctx.budget_rounds, ctx.budget_dollars)
        target = await _resolve_target(container, ctx)
        red = container.red_for(target_kind)
        oracles = container.oracles_for(target_kind)
        _retarget_oracles(oracles, target)

        # Reuse across runs (cr-b2): seed the attacker with the most evasive tactics the
        # strategy catalog distilled from PRIOR runs against this target type.
        if isinstance(red, Primable):
            async with session_scope() as session:
                known = await container.tactic_loader(session, target_kind)
            red.prime(known)
            if known:
                await sink.emit(run_id, "red_primed", {"n_tactics": len(known)})

        # Scheme-aware white-box (cr-b3): tell the attacker which checkers are actually in
        # the panel, so its white-box pass tries to beat the real ensemble.
        if isinstance(red, SchemeAware):
            red.note_scheme([str(o.kind) for o in oracles])

        # Bind a task-local sink so every LLM call the round makes is recorded (cr-b4).
        call_sink: list[LLMCallRecord] = []
        with record_into(call_sink):
            last_verdict: Verdict | None = None
            for i in range(budget_rounds):
                last_verdict = await _run_round(
                    container, spec, target, red, oracles, run_id, i, False, last_verdict)
                await _enforce_budget(run_id, budget_dollars)

            # White-box self-test pass: same red agent, the oracles' scheme revealed.
            await sink.emit(run_id, "white_box_started", {"run_id": str(run_id)})
            wb_caught = wb_wrong = 0
            for j in range(budget_rounds):
                verdict = await _run_round(
                    container, spec, target, red, oracles, run_id, budget_rounds + j, True,
                    last_verdict)
                last_verdict = verdict
                if verdict is not None and _held_out_fired(verdict):
                    wb_wrong += 1
                    if verdict.caught:
                        wb_caught += 1
                await _enforce_budget(run_id, budget_dollars)
            if wb_wrong:
                await _set_white_box_recall(run_id, wb_caught / wb_wrong)

        await _set_status(run_id, RunStatus.complete)
        await sink.emit(run_id, "run_complete", {
            "run_id": str(run_id), "rounds": budget_rounds,
            "white_box_recall": (wb_caught / wb_wrong) if wb_wrong else None,
        })
        _log.info("run_complete", run_id=str(run_id), rounds=budget_rounds,
                  white_box_recall=(wb_caught / wb_wrong) if wb_wrong else None)
    except _BudgetHaltError as halt:
        await _set_status(run_id, RunStatus.halted, error=halt.reason)
        await sink.emit(run_id, "budget_exceeded", {"run_id": str(run_id), "reason": halt.reason})
        _log.warning("run_budget_halt", run_id=str(run_id), reason=halt.reason)
    except Exception as exc:
        await _set_status(run_id, RunStatus.failed, error=repr(exc))
        await sink.emit(run_id, "run_failed", {"run_id": str(run_id), "error": repr(exc)})
        raise


async def _coevo_attack(
    container: Container, spec: SealedSpec, target: Target, red: RedAgent,
    oracles: list[Oracle], run_id: RunId, round_index: int, last_verdict: Verdict | None,
) -> tuple[Attack, Verdict | None]:
    """One attack against the current agent config: red -> submit -> verify -> persist.
    Returns the attack (so the loop can collect the ones that evaded) and the verdict."""
    attack = await red.propose(spec, run_id, round_index, last_verdict, white_box=False)
    result = await target.submit(attack.payload)
    verdict = await container.verify(oracles, spec, attack, result.output) if oracles else None
    await _persist_round(run_id, attack, result, verdict)
    await _persist_llm_calls(run_id, attack.attack_id, drain_records())
    await container.sink.emit(run_id, "attack", {
        "attack_id": str(attack.attack_id), "round": round_index, "tactic": attack.tactic,
        "payload": dict(attack.payload)})
    if verdict is not None:
        await container.sink.emit(run_id, "verdict", {
            "verdict_id": str(verdict.verdict_id), "attack_id": str(attack.attack_id),
            "outcome": str(verdict.outcome), "tally": verdict.tally,
            "threshold": verdict.threshold, "summary": verdict.audit.summary})
    return attack, verdict


async def run_coevolution(
    run_id: RunId, container: Container, *, coevo_rounds: int = 3, attacks_per_round: int = 3,
) -> None:
    """The co-evolutionary duel (cr-d3): for N rounds the red attacks the CURRENT agent
    config, the panel verifies, and the blue hardens the system prompt (a new
    agent_configs version, vendor model never retrained) — then the red attacks the
    hardened agent. Per-round ASR (fraction of attacks that slipped the panel) and
    detection are persisted so the dashboard can draw the co-evolution curves.

    The mock agent ignores its system prompt, so on the free demo the curves stay flat
    (honest); real movement needs CRUCIBLE_REAL_AGENT, where the agent follows the
    hardened prompt."""
    sink = container.sink
    await _set_status(run_id, RunStatus.running)
    await sink.emit(run_id, "run_started", {"run_id": str(run_id), "mode": "coevolution"})
    try:
        ctx = await _load_context(run_id)
        spec, target_kind, budget_dollars, agent_config_id = (
            ctx.spec, ctx.target_kind, ctx.budget_dollars, ctx.agent_config_id)
        red = container.red_for(target_kind)
        oracles = container.oracles_for(target_kind)
        blue = container.blue_for(target_kind)
        factory = container.agent_target_factory
        if blue is None or factory is None or not isinstance(blue, ConfigurableBlue):
            raise RuntimeError(
                "co-evolution requires an agent blue (ConfigurableBlue) + agent target factory")

        if isinstance(red, SchemeAware):
            red.note_scheme([str(o.kind) for o in oracles])
        if isinstance(red, Primable):
            async with session_scope() as session:
                known = await container.tactic_loader(session, target_kind)
            red.prime(known)

        # The duel starts from the run's agent config (BYO/demo, cr-e2) when present, else
        # the blue's built-in base; the blue versions it from there.
        if agent_config_id is not None:
            async with session_scope() as session:
                base_cfg = await load_agent_config(session, agent_config_id)
            blue.set_base(base_cfg)
        else:
            blue.reset()
        current_config = blue.current_config
        async with session_scope() as session:
            base_id = await save_agent_config(
                session, current_config, run_id=str(run_id), source="base")

        call_sink: list[LLMCallRecord] = []
        with record_into(call_sink):
            last_verdict: Verdict | None = None
            global_round = 0
            for r in range(coevo_rounds):
                target = factory(current_config)
                _retarget_oracles(oracles, target)
                total_caught = 0
                failed: list[Attack] = []        # attacks where the agent actually violated
                caught_failures = 0
                for _k in range(attacks_per_round):
                    attack, verdict = await _coevo_attack(
                        container, spec, target, red, oracles, run_id, global_round, last_verdict)
                    global_round += 1
                    last_verdict = verdict
                    if verdict is None:
                        continue
                    if verdict.caught:
                        total_caught += 1
                    # The held-out oracle is the closest thing to ground truth: when it
                    # fires, the agent genuinely failed (the attack worked).
                    if _held_out_fired(verdict):
                        failed.append(attack)
                        if verdict.caught:
                            caught_failures += 1
                # ASR = the agent's failure rate (attacks that made it violate); detection =
                # of those real failures, the fraction the panel caught.
                asr = len(failed) / attacks_per_round
                detection = caught_failures / len(failed) if failed else 1.0
                await sink.emit(run_id, "coevolution_round", {
                    "round": r, "asr": asr, "detection": detection,
                    "config_version": current_config.version, "n_attacks": attacks_per_round})

                # The blue hardens against the attacks that actually worked this round.
                patch = await blue.harden(spec, run_id, failed)
                await _persist_llm_calls(run_id, AttackId(patch.patch_id), drain_records())
                new_config = blue.current_config
                async with session_scope() as session:
                    if new_config.version != current_config.version:
                        await save_agent_config(
                            session, new_config, run_id=str(run_id), source="blue",
                            parent_config_id=base_id)
                    await save_coevolution_round(
                        session, run_id=str(run_id), round_index=r,
                        config_version=current_config.version, n_attacks=attacks_per_round,
                        n_caught=total_caught, asr=asr, detection=detection,
                        patch_id=patch.patch_id,
                        safe_before=patch.holdout_detection_before,
                        safe_after=patch.holdout_detection_after,
                        audit={"patch_summary": patch.summary, "validated": patch.validated,
                               "new_version": new_config.version,
                               "sections": patch.audit.detail.get("sections", [])})
                await sink.emit(run_id, "blue_patch", {
                    "round": r, "patch_id": patch.patch_id, "summary": patch.summary,
                    "safe_before": patch.holdout_detection_before,
                    "safe_after": patch.holdout_detection_after, "validated": patch.validated})
                current_config = new_config
                await _enforce_budget(run_id, budget_dollars)

        await _set_status(run_id, RunStatus.complete)
        await sink.emit(run_id, "run_complete", {
            "run_id": str(run_id), "rounds": coevo_rounds, "mode": "coevolution",
            "final_config_version": current_config.version})
        _log.info("coevolution_complete", run_id=str(run_id), rounds=coevo_rounds,
                  final_version=current_config.version)
    except _BudgetHaltError as halt:
        await _set_status(run_id, RunStatus.halted, error=halt.reason)
        await sink.emit(run_id, "budget_exceeded", {"run_id": str(run_id), "reason": halt.reason})
        _log.warning("coevolution_budget_halt", run_id=str(run_id), reason=halt.reason)
    except Exception as exc:
        await _set_status(run_id, RunStatus.failed, error=repr(exc))
        await sink.emit(run_id, "run_failed", {"run_id": str(run_id), "error": repr(exc)})
        raise
