"""Slice 0.5: ``crucible doctor`` — verify what a real run needs, each with a specific
fix, never a vague failure. Docker is required only if a code-shaped target is selected;
a fraud-only run reports Docker as "not required"."""

from __future__ import annotations

import argparse
from pathlib import Path

from crucible.runtime import (
    ProbeResult,
    claude_cli_available,
    docker_running,
    target_needs_docker,
)

_GREEN = "🟢"
_RED = "🔴"
_GREY = "⚪"


def _line(label: str, result: ProbeResult) -> str:
    mark = _GREEN if result.ok else _RED
    fix = f"\n      fix: {result.fix}" if (not result.ok and result.fix) else ""
    return f"  {mark} {label}: {result.detail}{fix}"


def _skip(label: str, why: str) -> str:
    return f"  {_GREY} {label}: not required ({why})"


def cmd_doctor(args: argparse.Namespace) -> int:
    target = getattr(args, "target", None)
    print("crucible doctor — prerequisites for a real run\n")
    checks: list[tuple[bool, str]] = []

    # Claude CLI (only real-LLM runs need it; mock runs do not) — advisory, not blocking.
    cli = claude_cli_available()
    checks.append((False, _line("Claude CLI (real-LLM runs)", cli)))

    # Docker: required only for code-shaped targets (the producer sandbox).
    if target is None or target_needs_docker(target):
        docker = docker_running()
        # If no target was named, Docker is advisory, not a hard fail.
        hard = target is not None and target_needs_docker(target)
        checks.append((hard and not docker.ok, _line("Docker daemon (producer sandbox)", docker)))
    else:
        checks.append((False, _skip("Docker daemon (producer sandbox)",
                                    f"target {target!r} runs no sandboxed code")))

    # Real model artifacts.
    for name in ("fraud-v1.lgb", "fraud-v2.lgb"):
        p = Path("artifacts") / name
        if p.exists():
            checks.append((False, _line(f"model artifact {name}",
                                        ProbeResult(True, f"{p} ({p.stat().st_size} bytes)"))))
        else:
            checks.append((False, _line(f"model artifact {name}", ProbeResult(
                False, f"{p} missing",
                "Train it: python -c 'from modules.targets.fraud.train import ensure_model; "
                f"ensure_model({name[7:8]})'"))))

    # Fraud dataset.
    csv = Path("data/creditcard.csv")
    if csv.exists():
        checks.append((False, _line("fraud dataset",
                                    ProbeResult(True, f"{csv} ({csv.stat().st_size} bytes)"))))
    else:
        checks.append((False, _line("fraud dataset", ProbeResult(
            False, f"{csv} missing", "Fetch it: python scripts/fetch_fraud_dataset.py"))))

    for _, text in checks:
        print(text)

    failed = sum(1 for hard, _ in checks if hard)
    print()
    if failed:
        print(f"{_RED} {failed} blocking prerequisite(s) for target "
              f"{target!r}. Fix the red lines above, then re-run.")
        return 1
    print(f"{_GREEN} ready" + (f" for a {target!r} run." if target else "."))
    return 0
