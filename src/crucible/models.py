"""Core data objects. Typed findings — no free-text-only results (per CLAUDE.md)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AttackClass(str, Enum):
    PROMPT_EXTRACTION = "prompt_extraction"
    SECRET_EXFIL = "secret_exfil"
    TOOL_ABUSE = "tool_abuse"
    JAILBREAK = "jailbreak"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Attack:
    id: str
    attack_class: AttackClass
    payload: str
    technique: str = "direct"          # direct | roleplay | paraphrase | base64 | ...
    origin: str = "library"            # library | mutation | catalog | llm
    lineage: list[str] = field(default_factory=list)


@dataclass
class Proof:
    """Why we know the attack succeeded. deterministic=True means ground truth."""

    kind: str          # canary_leak | tool_call | judge | guardrail_bypass
    detail: str
    deterministic: bool


@dataclass
class Finding:
    attack: Attack
    response: Response
    proof: Proof
    severity: Severity
    surface: str               # implicated AI-layer surface
    succeeded_seeds: int = 1
    total_seeds: int = 1


@dataclass
class Vulnerability:
    """A cluster of findings sharing one root cause."""

    id: str
    attack_class: AttackClass
    root_cause: str
    surface: str
    severity: Severity
    findings: list[Finding] = field(default_factory=list)


@dataclass
class FixCandidate:
    vulnerability_id: str
    layer: str                 # prompt | guardrail | tool_perm | code
    description: str
    diff: str
    config_patch: dict[str, Any]
    seen_pass: bool = False
    benign_pass: bool = False
    accepted: bool = False
    rounds: int = 0
    notes: str = ""


@dataclass
class EvalResult:
    held_out_catch_rate: float
    seen_catch_rate: float
    generalization_gap: float
    utility_delta: float
    per_class: dict[str, dict[str, float]] = field(default_factory=dict)
    residual: list[str] = field(default_factory=list)
    n_seen: int = 0
    n_held_out: int = 0
    n_benign: int = 0
    baseline_held_out_catch_rate: float = 0.0
