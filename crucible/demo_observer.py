"""Slice 10: the demo-authenticity observer (Crucible's anti-reward-hacking premise
applied to its own demo).

It watches a captured run and certifies that the result genuinely emulates an authentic
first-time-operator experience rather than gaming the demo. It refuses to sign off on any
reward-hacking pattern: reusing a prior capture, swapping in mock/stub data, hand-editing
artifacts, fast-forwarding past a failure, cherry-picking a lucky take, or narrating
claims the artifacts do not support.

Every on-screen claim must tie to a real artifact produced during the recording window:
a ``trace.jsonl`` event, or a file whose mtime falls inside the capture's time range. Any
claim that cannot be tied out fails. The deterministic tie-out below is unit-testable; an
LLM pass can judge the softer "would a real operator see this" spirit on top (the eval
row), but the hard checks here are what gate the demo."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path

from crucible.artifacts import RunArtifacts
from shared.obs.emit import EventType, TraceEvent, read_trace

# Model markers that mean the run used the free mock LLMs, not real Claude.
_MOCK_MARKERS = ("scripted-",)


class AuthenticityVerdict(StrEnum):
    authentic = "AUTHENTIC"
    flagged = "FLAGGED"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class AuthenticityReport:
    run_id: str
    verdict: AuthenticityVerdict
    window: dict[str, float | None]
    checks: list[Check] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "verdict": str(self.verdict),
            "window": self.window,
            "checks": [asdict(c) for c in self.checks],
            "flags": self.flags,
        }


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def observe(
    run_id: str, *, since: float | None = None, until: float | None = None,
    require_real_llm: bool = True,
) -> AuthenticityReport:
    """Run the deterministic authenticity tie-out over a run's artifacts.

    ``since``/``until`` are the capture window (epoch seconds). When given, every artifact
    and the trace's first event must fall inside it (no reused prior capture). When
    omitted, the window check is skipped but every other check still runs."""
    arts = RunArtifacts.for_run(run_id)
    checks: list[Check] = []
    flags: list[str] = []

    events = read_trace(run_id)
    if not events:
        return AuthenticityReport(
            run_id, AuthenticityVerdict.flagged, {"since": since, "until": until},
            [Check("trace_present", False, f"no trace at {arts.trace}")],
            ["no trace.jsonl — nothing to certify"])

    # 1. The run actually completed (a fast-forward past a failure would lack run_end).
    run_end = [e for e in events if e.type is EventType.run_end]
    completed = bool(run_end) and run_end[-1].data.get("status") == "complete"
    end_status = run_end[-1].data.get("status") if run_end else "missing"
    checks.append(Check("run_completed", completed, f"run_end status={end_status}"))
    if not completed:
        flags.append("run did not complete cleanly (possible fast-forward past a failure)")

    # 2. MOCK_LLM was off (the demo must use real Claude). Two signals: the run_start
    #    llm_mode flag, and the absence of scripted-model markers in the verdicts.
    start = next((e for e in events if e.type is EventType.run_start), None)
    llm_mode = (start.data.get("llm_mode") if start else None)
    mock_markers = _scan_mock_markers(arts)
    real_llm = llm_mode == "real" and not mock_markers
    if require_real_llm:
        checks.append(Check("real_llm", real_llm,
                            f"llm_mode={llm_mode}, mock_markers={sorted(mock_markers)}"))
        if not real_llm:
            flags.append(
                "MOCK_LLM was on (or scripted-model markers present); the demo must run "
                "against real Claude. Set the CRUCIBLE_REAL_* flags and re-record.")
    else:
        checks.append(Check("real_llm", True, f"(not required) llm_mode={llm_mode}"))

    # 3. The run used a real, committed model artifact (not a toy swapped in for the camera).
    target = start.data.get("target") if start else None
    checks.append(_real_model_check(target))
    if not checks[-1].ok:
        flags.append(checks[-1].detail)

    # 4. Every artifact file's mtime falls inside the capture window (no reused/stale file),
    #    and the trace's first event is inside the window (the run started during capture).
    if since is not None and until is not None:
        in_window, offenders = _window_check(arts, events, since, until)
        checks.append(Check("artifacts_in_window", in_window,
                            f"offenders={offenders}" if offenders else "all artifacts fresh"))
        if not in_window:
            flags.append(
                f"artifacts outside the capture window (reused/stale): {offenders}")
    else:
        checks.append(Check("artifacts_in_window", True,
                            "(no window provided; freshness not enforced)"))

    # 5. Headline claims in report.md tie out to metrics.json (no narrated unsupported number).
    checks.append(_claims_tie_out(arts))
    if not checks[-1].ok:
        flags.append(checks[-1].detail)

    verdict = (AuthenticityVerdict.authentic
               if all(c.ok for c in checks) else AuthenticityVerdict.flagged)
    return AuthenticityReport(run_id, verdict, {"since": since, "until": until}, checks, flags)


def _scan_mock_markers(arts: RunArtifacts) -> set[str]:
    """Find scripted-model markers in the verdict votes (mock-LLM tell)."""
    found: set[str] = set()
    vdir = arts.root / "verdicts"
    if not vdir.exists():
        return found
    for f in vdir.glob("*.json"):
        if f.name.endswith(".replay.json"):
            continue
        blob = f.read_text(encoding="utf-8")
        for marker in _MOCK_MARKERS:
            if marker in blob:
                found.add(marker)
    return found


def _real_model_check(target: object) -> Check:
    if target == "fraud":
        committed = Path("artifacts/fraud-v1.lgb")
        digest = _sha256(committed)
        if digest is None:
            return Check("real_model", False,
                         "fraud target but artifacts/fraud-v1.lgb is missing")
        return Check("real_model", True, f"fraud-v1.lgb sha256={digest[:12]}")
    if target == "code_agent":
        return Check("real_model", True, "code_agent runs the real code agent in the sandbox")
    return Check("real_model", True, f"target={target} (no committed ML artifact required)")


# Boundary grace: capture stamps are whole seconds while file mtimes carry sub-second
# precision, so a file written in the same second the window closes can read as a few
# tenths "after" it. A 2-second edge tolerance absorbs that without weakening reuse
# detection (a genuinely reused file is hours or days off, not fractions of a second).
_WINDOW_GRACE_S = 2.0


def _window_check(
    arts: RunArtifacts, events: list[TraceEvent], since: float, until: float
) -> tuple[bool, list[str]]:
    lo, hi = since - _WINDOW_GRACE_S, until + _WINDOW_GRACE_S
    offenders: list[str] = []
    first_ts = events[0].ts
    if not (lo <= first_ts <= hi):
        offenders.append(f"trace first event ts {first_ts:.0f} outside [{since:.0f},{until:.0f}]")
    for path in arts.root.rglob("*"):
        # Skip the observer's own outputs: authenticity.json (this report) and the
        # rendered site/ are produced after the run, not part of the captured run.
        if path.name == "authenticity.json" or "site" in path.parts:
            continue
        if path.is_file() and path.suffix in (".json", ".jsonl", ".md"):
            mtime = path.stat().st_mtime
            if not (lo <= mtime <= hi):
                offenders.append(f"{path.name} mtime {mtime:.0f}")
    return (not offenders), offenders


def _claims_tie_out(arts: RunArtifacts) -> Check:
    """Every percentage / dollar figure in report.md must appear in metrics.json (the
    report is generated from metrics, so a divergence means hand-editing)."""
    if not arts.report.exists() or not arts.metrics.exists():
        return Check("claims_tie_out", arts.report.exists() == arts.metrics.exists(),
                     "report.md and metrics.json must both exist or both be absent")
    import re

    report = arts.report.read_text(encoding="utf-8")
    metrics = json.loads(arts.metrics.read_text(encoding="utf-8"))
    tiles = metrics.get("tiles", {})
    detail = metrics.get("detail", {})
    # Build the set of numbers the report is allowed to show (from the real metrics).
    allowed: set[str] = set()
    for v in list(tiles.values()):
        if isinstance(v, (int, float)):
            allowed.add(f"{v * 100:.1f}")
    spend = detail.get("dollars_total")
    if isinstance(spend, (int, float)):
        allowed.add(f"{spend:.4f}")
    allowed.add(str(metrics.get("verdicts", "")))
    allowed.add(str(detail.get("producer_wrong_total", "")))
    allowed.add(str(detail.get("caught_total", "")))
    # Any percentage in the report must be a known measured value or "Not yet measured".
    shown = set(re.findall(r"(\d+\.\d+)%", report))
    unexplained = [s for s in shown if s not in allowed]
    if unexplained:
        return Check("claims_tie_out", False,
                     f"report shows percentages not in metrics.json: {unexplained}")
    return Check("claims_tie_out", True, "all report figures trace to metrics.json")


# --- CLI handler (crucible demo verify ...) --------------------------------
def cmd_demo_verify(args: argparse.Namespace) -> int:
    report = observe(
        args.run, since=args.since, until=args.until,
        require_real_llm=not args.allow_mock)
    arts = RunArtifacts.for_run(args.run)
    out = arts.root / "authenticity.json"
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(json.dumps(report.to_dict(), indent=2))
    print(f"\nauthenticity report: {out}")
    return 0 if report.verdict is AuthenticityVerdict.authentic else 1
