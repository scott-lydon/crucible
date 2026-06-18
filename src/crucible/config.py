"""Run configuration + the operator-owned safety attestation."""

from __future__ import annotations

from dataclasses import dataclass, field

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
