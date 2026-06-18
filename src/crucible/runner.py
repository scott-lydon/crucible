"""The orchestrator: Profile -> Attack -> Gate -> Fix -> Re-eval -> Report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .adapter import HTTPAdapter, TargetAdapter
from .attacks import AttackEngine
from .catalog import StrategyCatalog
from .config import CrucibleConfig
from .evaluate import EvalEngine
from .fix import FixEngine
from .gate import decide, present
from .llm import make_llm
from .models import AttackClass, EvalResult, Finding, FixCandidate, Vulnerability
from .oracles import OracleSuite
from .profiler import TargetProfile, profile_target
from .report import write_report
from .sample_target import BENIGN_PROMPTS, get_builtin_target


@dataclass
class RunResult:
    target: str
    mode: str
    profile: TargetProfile
    findings: list[Finding] = field(default_factory=list)
    vulnerabilities: list[Vulnerability] = field(default_factory=list)
    fixes: list[FixCandidate] = field(default_factory=list)
    eval_result: EvalResult | None = None
    patch: dict[str, Any] = field(default_factory=dict)
    narration: list[str] = field(default_factory=list)
    report_paths: tuple[str, str] | None = None


def build_target(spec: str) -> TargetAdapter:
    if spec.startswith("builtin:") or spec == "acmebot":
        return get_builtin_target(spec)
    if spec.startswith("browser:"):
        from .browser import BrowserAdapter  # optional dep (playwright)
        return BrowserAdapter(spec[len("browser:"):])
    if spec.startswith(("http://", "https://")):
        return HTTPAdapter(spec)
    raise ValueError(f"unsupported target spec: {spec!r} "
                     "(use builtin:acmebot, browser:<url>, or an http(s):// endpoint)")


def run(config: CrucibleConfig) -> RunResult:
    config.authorize()
    narration: list[str] = []

    def narrate(msg: str) -> None:
        narration.append(msg)
        if config.verbose:
            print(msg, flush=True)

    target = build_target(config.target)
    profile = profile_target(target)
    narrate(f"▶ profiled target: access={profile.access}, "
            f"tools={[t.get('name') for t in profile.tools]}, "
            f"secrets_known={len(profile.secrets)}")

    llm = make_llm(config.llm, config.model)
    if config.llm == "anthropic":
        narrate(f"  LLM: anthropic {'available' if llm.available else 'UNAVAILABLE → deterministic'}")
    oracles = OracleSuite(secrets=profile.secrets, refund_limit=profile.refund_limit, llm=llm)
    catalog = StrategyCatalog(path=config.catalog_path)
    classes = [AttackClass(c) for c in config.classes]

    narrate("\n========== ATTACK ==========")
    engine = AttackEngine(target, oracles, catalog=catalog, seeds=config.seeds, narrator=narrate)
    findings = engine.run(classes)

    fixer = FixEngine(
        target, oracles, BENIGN_PROMPTS,
        prefer_structural=config.prefer_structural,
        max_rounds=config.max_fix_rounds, narrator=narrate,
    )
    vulns = fixer.cluster(findings)
    present(findings, vulns, narrate)

    fixes: list[FixCandidate] = []
    patch: dict[str, Any] = {}
    eval_result: EvalResult | None = None

    if findings and decide(config.mode, config.assume_yes):
        narrate("\n========== FIX ==========")
        fixes, patch = fixer.fix(vulns, profile)
        fixed_target = target.clone_with_config(patch) or target
        narrate("\n========== RE-EVAL (held-out) ==========")
        evaler = EvalEngine(oracles, BENIGN_PROMPTS, seeds=config.seeds)
        eval_result = evaler.evaluate(target, fixed_target, findings, classes)
        narrate(f"held-out catch rate: {eval_result.held_out_catch_rate:.0%}  "
                f"(gap {eval_result.generalization_gap:+.0%}, "
                f"utility {eval_result.utility_delta:+.0%})")
    else:
        narrate("gate: not proceeding (no approval, or no findings).")

    catalog.close()
    record = RunResult(
        target=config.target, mode=config.mode, profile=profile, findings=findings,
        vulnerabilities=vulns, fixes=fixes, eval_result=eval_result, patch=patch,
        narration=narration,
    )
    narrate("\n========== REPORT ==========")
    paths = write_report(config.out_dir, record)
    record.report_paths = paths
    narrate(f"wrote {paths[0]} and {paths[1]}")
    return record
