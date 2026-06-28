"""Resolve a :class:`SealedSpec` for a CLI run.

Either the operator passes ``--spec <file.yaml>`` (a sealed-spec YAML, parsed by
``SealedSpec.from_yaml``), or we fall back to a built-in demo human-spec compiled with
the deterministic compiler so a first run needs no authoring. The demo specs are the
same plain-English specs the web demos use, so the CLI and web agree on the job."""

from __future__ import annotations

from pathlib import Path

from modules.spec.compiler import deterministic_compile
from modules.targets.agent import CODE_AGENT_DEMO_SPEC, demo_spec
from orchestrator.interfaces import Target
from shared.types.enums import Shape
from shared.types.sealed_spec import HumanSpec, SealedSpec

# Built-in plain-English specs per target kind, for a zero-authoring first run.
_DEMO_HUMAN_SPECS: dict[str, HumanSpec] = {
    "code_agent": CODE_AGENT_DEMO_SPEC,
    "agent": demo_spec("support-bot"),
    "dummy": HumanSpec(
        task="Score each transaction's fraud probability and label it fraud or not.",
        failure_conditions=(
            "label a clearly fraudulent transaction as legitimate",
            "return a probability outside the range 0 to 1",
        ),
    ),
    "fraud": HumanSpec(
        task="Classify card transactions as fraudulent or legitimate from their features.",
        failure_conditions=(
            "pass a known-fraud transaction as legitimate under small feature perturbation",
            "return inconsistent scores for transactions that differ only by a monotone shift",
        ),
    ),
}


class SpecResolutionError(ValueError):
    """A spec file was given but does not parse, or no built-in spec exists for the
    target. Names the path and the fix."""


def builtin_human_spec(target_kind: str) -> HumanSpec | None:
    return _DEMO_HUMAN_SPECS.get(target_kind)


def resolve_sealed_spec(target: Target, spec_path: str | None) -> SealedSpec:
    """Return the SealedSpec for this run. From the YAML file when given, else the
    built-in demo spec compiled deterministically for the target's shape."""
    if spec_path:
        path = Path(spec_path)
        if not path.exists():
            raise SpecResolutionError(
                f"spec file not found: {path}. Fix: pass --spec with a readable YAML path.")
        try:
            return SealedSpec.from_yaml(path.read_text(encoding="utf-8"))
        except Exception as exc:  # parse/shape errors become a typed, path-named failure
            raise SpecResolutionError(f"invalid spec {path}: {exc}") from exc

    human = builtin_human_spec(target.kind)
    if human is None:
        raise SpecResolutionError(
            f"no built-in spec for target {target.kind!r}; "
            f"pass --spec <file.yaml>. Built-in targets: {sorted(_DEMO_HUMAN_SPECS)}.")
    shape = target.shape if isinstance(target.shape, Shape) else Shape(target.shape)
    return deterministic_compile(human, target_kind=target.kind, shape=shape)
