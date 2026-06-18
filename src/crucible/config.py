"""Run configuration + the operator-owned safety attestation."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path

from .models import AttackClass

ALL_CLASSES = [c.value for c in AttackClass]


class NotAuthorizedError(RuntimeError):
    """Raised when the run is not attested as operator-owned."""


@dataclass
class CrucibleConfig:
    target: str = "builtin:acmebot"
    mode: str = "approve"                 # approve | auto
    classes: list[str] = field(default_factory=lambda: list(ALL_CLASSES))
    seeds: int = 3                        # attempts per attack (matters for real, stochastic LLMs)
    max_fix_rounds: int = 3
    operator_owned: bool = False          # MUST be True to run (attestation)
    prefer_structural: bool = True        # prefer guardrail/tool fixes over prompt-only
    out_dir: str = "runs"
    llm: str = "deterministic"            # deterministic | anthropic
    model: str = "claude-sonnet-4-6"      # used only when llm == anthropic
    assume_yes: bool = False              # non-interactive approve
    verbose: bool = True                  # stream narration to stdout
    catalog_path: str = ".crucible/catalog.db"
    multi_turn: bool = False              # also run a multi-turn (crescendo) attacker
    multi_turn_turns: int = 5
    search: bool = False                  # also run a best-of-N / TAP-style adaptive search
    payloads_file: str = ""               # extra attack payloads JSON {class: [str]} (BYO corpus)
    max_attacks: int = 0                  # cap library attacks per class (0 = no cap); for live cost
    http: dict = field(default_factory=dict)  # HTTPAdapter config (headers, paths) for http targets

    def authorize(self) -> None:
        """Refuse to run unless the operator attests they own the target.

        Golden rule #1: operator-owned targets only. This is a defensive tool.
        """
        if not self.operator_owned:
            raise NotAuthorizedError(
                "Refusing to run: you must attest that you own (or are explicitly "
                "authorized to test) this target. Pass --i-own-this-target.\n"
                "Crucible is a defensive tool for hardening your own AI agents."
            )
        if self.target.startswith(("http://", "https://")) and not self.target.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            # A remote URL is allowed only with explicit attestation already checked above,
            # but we keep a visible reminder in the audit trail.
            pass


CONFIG_TEMPLATE = {
    "_comment": "Crucible run config — set your target, then `crucible run --config crucible.json`.",
    "target": "builtin:acmebot",
    "mode": "approve",
    "classes": list(ALL_CLASSES),
    "seeds": 3,
    "operator_owned": False,
    "llm": "deterministic",
    "model": "claude-sonnet-4-6",
    "out_dir": "runs",
    "max_attacks": 0,
}


def config_from_file(path: str) -> CrucibleConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {f.name for f in dataclasses.fields(CrucibleConfig)}
    return CrucibleConfig(**{k: v for k, v in data.items() if k in names})


def write_config_template(path: str) -> None:
    Path(path).write_text(json.dumps(CONFIG_TEMPLATE, indent=2) + "\n", encoding="utf-8")
