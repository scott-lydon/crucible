"""Slice 8b: per-component eval harness.

``crucible eval <component>`` runs that component's eval (dataset + metric + threshold)
from the test matrix, on real LLM calls, invoking the component through the SAME wiring
as the focus subcommands (Slice 5b), and writes ``artifacts/evals/<component>/<ts>.json``
plus a one-line pass/fail with the measured number vs the threshold.

Eval datasets are real recorded inputs + ground-truth labels. A missing dataset is a
typed error naming the path, never a silent skip (the no-fake-data rule)."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.obs.emit import artifacts_root


class EvalDatasetMissingError(FileNotFoundError):
    """The eval dataset is absent. Names the path and how to provide it."""

    def __init__(self, component: str, path: Path) -> None:
        super().__init__(
            f"eval dataset for {component!r} not found at {path}. "
            f"Provide a real labeled set (recorded inputs + ground-truth labels) at that "
            f"path, one JSON object per line: {{\"input\": ..., \"label\": ...}}. "
            f"Evals never run on synthetic placeholders.")
        self.component = component
        self.path = path


@dataclass(frozen=True)
class EvalSpec:
    component: str
    target_kind: str          # which wired ensemble the component resolves through
    metric: str               # human label of the measured quantity
    threshold: float          # pass iff measured >= threshold
    dataset: str              # filename under artifacts/evals/datasets/


# The eval rows from the test matrix. Datasets live under artifacts/evals/datasets/.
EVAL_REGISTRY: dict[str, EvalSpec] = {
    "llm_judge": EvalSpec("llm_judge", "agent", "judge precision/recall vs labels", 0.7,
                          "llm_judge.jsonl"),
    "held_out": EvalSpec("held_out", "agent", "held-out catch precision/recall", 0.7,
                         "held_out.jsonl"),
    "differential": EvalSpec("differential", "agent", "divergence precision/recall", 0.6,
                             "differential.jsonl"),
    "metamorphic": EvalSpec("metamorphic", "agent", "paraphrase-flip detection", 0.6,
                            "metamorphic.jsonl"),
    "property_fuzz": EvalSpec("property_fuzz", "agent", "counterexample detection", 0.6,
                              "property_fuzz.jsonl"),
    "red_search": EvalSpec("red_search", "fraud", "attack success rate on seed set", 0.3,
                           "red_search.jsonl"),
    "suitability": EvalSpec("suitability", "agent", "grade agreement vs labeled fit set", 0.7,
                            "suitability.jsonl"),
}


def _dataset_path(spec: EvalSpec) -> Path:
    return artifacts_root() / "evals" / "datasets" / spec.dataset


def _load_dataset(spec: EvalSpec) -> list[dict[str, Any]]:
    path = _dataset_path(spec)
    if not path.exists():
        raise EvalDatasetMissingError(spec.component, path)
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not rows:
        raise EvalDatasetMissingError(spec.component, path)
    return rows


def _score_oracle(spec: EvalSpec, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the wired oracle over each labeled row and compute precision/recall of the
    catch. Each row: {input, output, label} where label True == producer is wrong."""
    from crucible.focus import resolve_oracle
    from crucible.specs import resolve_sealed_spec
    from orchestrator.interfaces import Retargetable
    from orchestrator.wiring import get_container
    from shared.types.core import Attack
    from shared.types.ids import AttackId, RunId, new_id

    container = get_container()
    oracle = resolve_oracle(spec.target_kind, spec.component, container)
    sealed = resolve_sealed_spec(container.get_target(spec.target_kind), None)
    if isinstance(oracle, Retargetable):
        oracle.set_resubmit(container.get_target(spec.target_kind).submit)

    tp = fp = tn = fn = 0

    async def _vote(row: dict[str, Any]) -> bool:
        attack = Attack(attack_id=AttackId(new_id("atk")), run_id=RunId("run_eval"), round_index=0,
                        tactic="eval", payload=dict(row.get("input", {})),
                        rationale="eval", seed="eval")
        v = await oracle.vote(sealed, attack, row.get("output", {}))
        return v.fired

    for row in rows:
        fired = asyncio.run(_vote(row))
        label = bool(row.get("label"))
        if fired and label:
            tp += 1
        elif fired and not label:
            fp += 1
        elif not fired and not label:
            tn += 1
        else:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else None)
    return {"precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "tn": tn, "fn": fn, "n": len(rows)}


def run_eval(component: str, *, now: float | None = None) -> dict[str, Any]:
    if component not in EVAL_REGISTRY:
        raise KeyError(f"unknown eval component {component!r}; "
                       f"known: {sorted(EVAL_REGISTRY)}")
    spec = EVAL_REGISTRY[component]
    rows = _load_dataset(spec)                       # typed error if missing
    scored = _score_oracle(spec, rows)
    measured = scored.get("f1") if scored.get("f1") is not None else scored.get("recall")
    passed = measured is not None and measured >= spec.threshold
    ts = now if now is not None else time.time()
    result = {
        "component": component, "metric": spec.metric, "threshold": spec.threshold,
        "measured": measured, "passed": passed, "ts": ts, "scores": scored,
        "dataset": str(_dataset_path(spec))}
    out_dir = artifacts_root() / "evals" / component
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{int(ts)}.json"
    out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    result["artifact"] = str(out)
    return result


def cmd_eval(args: argparse.Namespace) -> int:
    components = sorted(EVAL_REGISTRY) if args.component == "all" else [args.component]
    failures = 0
    for component in components:
        try:
            result = run_eval(component)
        except (EvalDatasetMissingError, KeyError) as exc:
            print(f"  ✗ {component}: {exc}")
            failures += 1
            continue
        mark = "✓" if result["passed"] else "✗"
        measured = result["measured"]
        m_text = "n/a" if measured is None else f"{measured:.3f}"
        print(f"  {mark} {component}: {m_text} vs threshold {result['threshold']} "
              f"-> {result['artifact']}")
        if not result["passed"]:
            failures += 1
    return 1 if failures else 0
