"""``FileTraceSink``: a :class:`~orchestrator.interfaces.measure.MeasureSink` that drives
the observability spine (:class:`shared.obs.emit.Tracer`).

This is the SAME seam the mainline loop already emits through, so wiring it in means the
file trace and terminal stream are produced by the exact path the web run uses, never a
second emit path that can drift. The loop keeps emitting its legacy string kinds; this
sink (a) forwards them to an inner sink so the dashboard SSE / health route are untouched
(surgical: the web front-end is unchanged) and (b) translates them into the closed
``EventType`` vocabulary for the durable JSONL trace and the live terminal.

A single ``verdict`` emit fans into one ``oracle_fired`` per vote plus one ``verdict``, so
the trace carries per-oracle granularity without the loop having to know about it."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any

from modules.measure.sink import InMemoryMeasureSink
from orchestrator.interfaces.measure import HealthProbe, MeasureSink
from shared.obs.emit import EventType, Tracer
from shared.types.ids import RunId
from shared.types.results import HealthStatus


class FileTraceSink:
    """MeasureSink whose every event also lands in ``trace.jsonl`` and the terminal.

    Health probes and SSE subscription delegate to an inner in-memory sink so the
    existing web surface keeps working when this sink is used in-process."""

    def __init__(self, tracer: Tracer, inner: MeasureSink | None = None) -> None:
        self.tracer = tracer
        self.inner = inner if inner is not None else InMemoryMeasureSink()
        self._last_round: int | None = None

    async def emit(self, run_id: RunId, kind: str, payload: Mapping[str, Any]) -> None:
        # Always forward verbatim to the inner sink (dashboard SSE, history).
        await self.inner.emit(run_id, kind, payload)
        # Translate into the rich, closed EventType vocabulary for file + terminal.
        for event_type, data in self._translate(kind, dict(payload)):
            self.tracer.emit(event_type, data)

    def _translate(
        self, kind: str, p: dict[str, Any]
    ) -> list[tuple[EventType, dict[str, Any]]]:
        out: list[tuple[EventType, dict[str, Any]]] = []
        # run lifecycle (run_start / run_end / halt) is owned by the CLI runner so it is
        # single-sourced and the final values reflect the post-loop artifacts; the loop's
        # own run_started / run_complete / budget_exceeded / run_failed land in the inner
        # sink only (dashboard), not as duplicate file events.
        if kind == "attack":
            round_index = p.get("round")
            if round_index != self._last_round:
                self._last_round = round_index
                out.append((EventType.round_start, {
                    "round": round_index, "white_box": p.get("white_box", False)}))
            out.append((EventType.red_tactic_proposed, {
                "tactic": p.get("tactic"), "attack_id": p.get("attack_id"),
                "white_box": p.get("white_box", False),
                "rationale": p.get("rationale", "")}))
            out.append((EventType.target_queried, {"attack_id": p.get("attack_id")}))
        elif kind == "producer_output":
            out.append((EventType.target_scored, {
                "attack_id": p.get("attack_id"), "output": p.get("output", {})}))
        elif kind == "verdict":
            for vote in p.get("votes", []):
                fired = bool(vote.get("fired"))
                out.append((EventType.oracle_fired, {
                    "oracle": vote.get("oracle"), "fired": fired,
                    # passed = the producer satisfied this oracle's check (oracle did
                    # not fire). 🟢 passed, 🔴 the oracle caught a violation.
                    "passed": not fired, "obligation": vote.get("obligation"),
                    "reason": vote.get("reason", "")}))
            out.append((EventType.verdict, {
                "verdict_id": p.get("verdict_id"), "attack_id": p.get("attack_id"),
                "outcome": p.get("outcome"), "tally": p.get("tally"),
                "threshold": p.get("threshold"), "white_box": p.get("white_box", False),
                "replay": p.get("replay", False), "summary": p.get("summary", "")}))
        elif kind == "coevolution_round":
            out.append((EventType.metric_update, {
                "round": p.get("round"), "asr": p.get("asr"),
                "detection": p.get("detection"),
                "config_version": p.get("config_version")}))
        elif kind == "blue_patch":
            out.append((EventType.blue_patch_proposed, {
                "round": p.get("round"), "patch_id": p.get("patch_id"),
                "summary": p.get("summary", "")}))
            out.append((EventType.holdout_validated, {
                "before": p.get("safe_before"), "after": p.get("safe_after"),
                "validated": p.get("validated")}))
        elif kind == "run_complete":
            wb = p.get("white_box_recall")
            if wb is not None:
                out.append((EventType.metric_update, {"recall": wb, "kind": "white_box_recall"}))
        elif kind == "budget_exceeded":
            out.append((EventType.halt_check, {"halt": True, "reason": p.get("reason")}))
        # red_primed, white_box_started, run_started, run_failed: inner sink only.
        return out

    def subscribe(self, run_id: RunId) -> AsyncIterator[Mapping[str, Any]]:
        return self.inner.subscribe(run_id)

    def register_health_probe(self, name: str, probe: HealthProbe) -> None:
        self.inner.register_health_probe(name, probe)

    async def run_health(self) -> Mapping[str, HealthStatus]:
        return await self.inner.run_health()
