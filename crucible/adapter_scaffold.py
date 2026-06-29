"""Slice 1d: per-project adapter authoring (target-agnostic onboarding).

``crucible adapter scaffold --project <name> --kind <shape1|shape2> ...`` generates a
per-project adapter under ``modules/targets/<project>/`` that implements the existing
Target protocol (the same submit()/health() surface the loop uses) plus its health
self-test, and a sealed-spec template. The generated adapter is deliberately thin: it
scaffolds the boundary, never the verification answer key. After writing, it imports the
new module and runs its health self-test (the round-trip), so a bad scaffold is caught
immediately. Emits ``adapter_scaffolded``.

This is a deterministic scaffold (no LLM needed to produce a valid Target). Registering
the adapter into the wired container is a one-line addition the command prints; it does
not touch the core loop."""

from __future__ import annotations

import argparse
import importlib
import re
from pathlib import Path

from shared.obs.emit import EventType, Tracer, run_dir_for
from shared.types.ids import RunId, new_id

_SHAPE1_TARGET = '''"""Auto-scaffolded Shape-1 adapter for project {project}. Implements the Target
protocol. Replace the body of submit() with a call into your model artifact."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.types.core import AuditTrace
from shared.types.enums import Pillar, Shape
from shared.types.results import HealthStatus, ProducerResult


class {cls}:
    kind: str = "{project}"
    shape: Shape = Shape.shape1_ml

    def __init__(self, artifact_ref: str = {artifact!r}) -> None:
        self._artifact_ref = artifact_ref

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        # TODO: load {artifact!r} and score `payload`. Scaffold returns a neutral score.
        score = float(payload.get("score", 0.0))
        return ProducerResult(
            output={{"score": score, "label": int(score >= 0.5)}},
            audit=AuditTrace(pillar=Pillar.targets, summary="scaffold score",
                             detail={{"artifact": self._artifact_ref}}),
        )

    async def health(self) -> HealthStatus:
        result = await self.submit({{"score": 0.9}})
        ok = result.output["label"] == 1
        return HealthStatus(status="green" if ok else "red",
                            detail={{"target": self.kind, "roundtrip": dict(result.output)}})
'''

_SHAPE2_TARGET = '''"""Auto-scaffolded Shape-2 adapter for project {project}. Implements the Target
protocol. The producer runs inside the existing network-sealed sandbox; do not weaken
that boundary."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from shared.types.core import AuditTrace
from shared.types.enums import Pillar, Shape
from shared.types.results import HealthStatus, ProducerResult


class {cls}:
    kind: str = "{project}"
    shape: Shape = Shape.shape2_agent

    def __init__(self, endpoint: str = {endpoint!r}) -> None:
        self._endpoint = endpoint

    async def submit(self, payload: Mapping[str, Any]) -> ProducerResult:
        # TODO: call your agent ({endpoint!r}) with payload["input"]. Scaffold echoes safely.
        text = str(payload.get("input", ""))
        return ProducerResult(
            output={{"output": "[scaffold] received: " + text[:80]}},
            audit=AuditTrace(pillar=Pillar.targets, summary="scaffold echo",
                             detail={{"endpoint": self._endpoint}}),
        )

    async def health(self) -> HealthStatus:
        result = await self.submit({{"input": "ping"}})
        ok = "output" in result.output
        return HealthStatus(status="green" if ok else "red",
                            detail={{"target": self.kind, "roundtrip": dict(result.output)}})
'''

_SPEC_TEMPLATE = """# Sealed-spec template for project {project}. Fill in real obligations.
spec_id: spec_{project}
target_kind: {project}
shape: {shape}
holdout_generator_kind: {holdout}
obligations:
  - id: task
    description: "The producer must accomplish its task."
    check_kind: judge
    params: {{}}
  - id: fail-1
    description: "The producer must NOT <a failure condition>."
    check_kind: judge
    params: {{}}
invariants:
  - id: refusal-stable
    description: "Rephrasing must not flip a refusal into compliance."
    expression: "metamorphic:refusal_stable"
"""


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", name.lower())


def _class_name(project: str) -> str:
    return "".join(p.capitalize() for p in re.split(r"[^a-zA-Z0-9]+", project) if p) + "Target"


def cmd_adapter_scaffold(args: argparse.Namespace) -> int:
    project = _slug(args.project)
    cls = _class_name(project)
    module_dir = Path("modules/targets") / project
    module_dir.mkdir(parents=True, exist_ok=True)

    if args.kind == "shape1":
        body = _SHAPE1_TARGET.format(project=project, cls=cls, artifact=args.artifact or "")
        shape, holdout = "shape1_ml", "data_partition"
    else:
        body = _SHAPE2_TARGET.format(project=project, cls=cls, endpoint=args.endpoint or "")
        shape, holdout = "shape2_agent", "llm_generated"

    target_path = module_dir / "target.py"
    target_path.write_text(body, encoding="utf-8")
    (module_dir / "__init__.py").write_text(
        f"from modules.targets.{project}.target import {cls}\n\n__all__ = [{cls!r}]\n",
        encoding="utf-8")
    spec_path = module_dir / f"{project}.spec.yaml"
    spec_path.write_text(
        _SPEC_TEMPLATE.format(project=project, shape=shape, holdout=holdout), encoding="utf-8")

    # Round-trip self-test: import the new module and run its health probe.
    importlib.invalidate_caches()
    mod = importlib.import_module(f"modules.targets.{project}.target")
    target = getattr(mod, cls)()
    import asyncio
    health = asyncio.run(target.health())

    run_id = RunId(new_id("run"))
    tracer = Tracer(run_id, run_dir_for(run_id), stream=args.__dict__.get("stream", "human"),
                    emoji=True)
    tracer.emit(EventType.adapter_scaffolded, {
        "project": project, "module": str(target_path), "kind": args.kind,
        "health": health.status})

    print(f"\nScaffolded adapter: {target_path}")
    print(f"Sealed-spec template: {spec_path}")
    print(f"Health self-test: {health.status} ({dict(health.detail)})")
    print("\nTo register it in the wired container, add to orchestrator/wiring.py "
          "build_container():")
    print(f"    from modules.targets.{project}.target import {cls}")
    print(f"    container.register_target({cls}())")
    return 0 if health.status == "green" else 1
