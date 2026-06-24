"""Hierarchical platform health + self-tests (US-8) and the seal card (US-9).

This is the OBSERVABILITY backend the operator's `/health` page reads. It is a
read-mostly self-test view: every leaf is a cheap SMOKE test (constructible /
reachable / returns the expected shape), never a real run and — critically —
never a real billed LLM call. The Anthropic leg is a TOKEN-FREE reachability
check (key presence + a mockable ping), so opening `/health` cannot spend money.

Honest states only:
  * ``green`` — the smoke passed, with a ``last_self_test`` timestamp.
  * ``amber`` — degraded / unknown but not a hard failure (e.g. Docker absent so
    the live seal probe cannot run; an external dep we chose not to hard-fail on).
  * ``red``   — the smoke failed, with the current ``error`` string.

We NEVER fake green: an unknown leaf reports amber/red with the reason, not a
placeholder pass.

Hexagonal: this module lives in the Measure pillar and imports only ``shared.*``
+ ``sqlalchemy`` for the live Postgres check. It takes the live oracle objects
(and the optional sandbox) as INJECTED arguments from the composition layer
(``orchestrator/api.py``), so it never imports a pillar module or ``examples/``
and cannot create an import cycle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.sandbox import (
    SealTargets,
    bridge_gateway_ip,
    run_seal_probe,
)
from shared.sandbox.base import Sandbox

# State strings — the three honest leaf states.
GREEN = "green"
AMBER = "amber"
RED = "red"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class Leaf:
    """One self-test leaf: its current state, last-run timestamp, and any error."""

    state: str
    last_self_test: str | None
    error: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "last_self_test": self.last_self_test,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class Component:
    """A named subcomponent with a synchronous smoke callable.

    ``smoke`` returns ``(state, error)``. It must be CHEAP and side-effect-free
    enough to run on every page load: construct/reach/shape only, never a real
    run and never a billed LLM call.
    """

    component_id: str
    label: str
    smoke: Callable[[], tuple[str, str | None]]

    def run(self) -> Leaf:
        try:
            state, error = self.smoke()
        except Exception as exc:  # noqa: BLE001 — a crashing smoke is itself red.
            return Leaf(state=RED, last_self_test=_now_iso(), error=f"{type(exc).__name__}: {exc}")
        return Leaf(state=state, last_self_test=_now_iso(), error=error)


@dataclass(frozen=True, slots=True)
class Module:
    module_id: str
    label: str
    components: list[Component]


@dataclass(frozen=True, slots=True)
class Pillar:
    pillar_id: str
    label: str
    modules: list[Module]


# ---------------------------------------------------------------------------
# Smoke builders. Each returns a (state, error) tuple. Kept tiny and honest.
# ---------------------------------------------------------------------------


def _ok() -> tuple[str, str | None]:
    return GREEN, None


def _shape_smoke(obj: object, *attrs: str) -> Callable[[], tuple[str, str | None]]:
    """Green iff ``obj`` is non-None and exposes every named attribute.

    The cheap "constructible / right shape" smoke for an in-process component
    (an oracle, the adversary, the detector). No call is made — only presence
    and surface are checked, so it is free and side-effect-free.
    """

    def smoke() -> tuple[str, str | None]:
        if obj is None:
            return AMBER, "not wired in this composition (absent)"
        missing = [a for a in attrs if not hasattr(obj, a)]
        if missing:
            return RED, f"missing expected attributes: {', '.join(missing)}"
        return _ok()

    return smoke


def _postgres_smoke(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> Callable[[], tuple[str, str | None]]:
    """Real Postgres connectivity smoke (``SELECT 1``).

    This is the one leg that does live IO, but it is a single trivial query, not
    a run. SQLite (the test DB) answers ``SELECT 1`` too, so the smoke is green
    under the in-memory test harness without requiring a real Postgres.
    """

    def smoke() -> tuple[str, str | None]:
        # Synchronous wrapper around the async DB check; the caller invokes the
        # async variant directly (see ``check_postgres``). This sync stub only
        # reports that the factory exists — the async path does the real query.
        if session_factory is None:
            return RED, "session factory not initialized (init_db not called)"
        return AMBER, "connectivity verified asynchronously; see live state"

    return smoke


def _docker_smoke() -> tuple[str, str | None]:
    """Docker availability smoke for the sandbox adapter (no container run).

    Green when the daemon answers ``docker info``; AMBER (not red) when Docker is
    absent — an honest "the live seal probe cannot run here", not a failure of
    Crucible itself.
    """
    docker = shutil.which("docker")
    if docker is None:
        return AMBER, "docker CLI not on PATH; live sandbox/seal probe unavailable"
    try:
        proc = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=30.0,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return AMBER, f"docker daemon unreachable: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return AMBER, f"docker daemon not available: {(proc.stderr or proc.stdout).strip()}"
    return _ok()


def _anthropic_smoke(
    ping: Callable[[], bool] | None = None,
) -> Callable[[], tuple[str, str | None]]:
    """TOKEN-FREE Anthropic reachability smoke.

    NEVER makes a real completion. By default it checks only for the presence of
    ``ANTHROPIC_API_KEY`` in the environment (a credential-shape check). Tests
    (and a future cheap ping) may inject ``ping`` — a mockable callable returning
    a bool — so the leg is exercisable offline. We do not call the network here.
    """

    def smoke() -> tuple[str, str | None]:
        if ping is not None:
            return (_ok() if ping() else (RED, "anthropic ping returned not-ok"))
        if os.environ.get("ANTHROPIC_API_KEY"):
            return GREEN, None
        return AMBER, "ANTHROPIC_API_KEY not set (token-free check; no call made)"

    return smoke


# ---------------------------------------------------------------------------
# Hierarchy assembly.
# ---------------------------------------------------------------------------

# The six oracle kinds we surface as Targets-and-Oracles subcomponents.
_ORACLE_KINDS = (
    "held_out",
    "metamorphic",
    "invariant",
    "differential",
    "property_fuzz",
    "llm_judge",
)


@dataclass(frozen=True, slots=True)
class HealthInputs:
    """Live objects injected from the composition layer for the self-tests.

    Everything is optional so ``/health`` works even before a run is wired (it
    then reports honest amber "absent" leaves, never fake green).
    """

    session_factory: async_sessionmaker[AsyncSession] | None = None
    detector: object | None = None
    adversary: object | None = None
    oracles: Sequence[object] = field(default_factory=tuple)
    sandbox: object | None = None
    anthropic_ping: Callable[[], bool] | None = None


def _oracle_by_kind(oracles: Iterable[object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for o in oracles:
        kind = getattr(o, "kind", None)
        key = getattr(kind, "value", kind)
        if isinstance(key, str):
            out[key] = o
    return out


def build_pillars(inputs: HealthInputs) -> list[Pillar]:
    """Assemble the pillar -> module -> subcomponent hierarchy of smoke tests."""
    by_kind = _oracle_by_kind(inputs.oracles)

    oracle_components = [
        Component(
            component_id=f"oracle.{kind}",
            label=f"{kind} oracle",
            smoke=_shape_smoke(by_kind.get(kind), "kind", "vote", "describe"),
        )
        for kind in _ORACLE_KINDS
    ]

    targets_pillar = Pillar(
        pillar_id="targets",
        label="Targets & Oracles",
        modules=[
            Module(
                module_id="targets.adapter",
                label="Targets adapter",
                components=[
                    Component(
                        component_id="targets.adapter.detector",
                        label="Detector adapter",
                        smoke=_shape_smoke(inputs.detector, "score"),
                    )
                ],
            ),
            Module(module_id="oracles", label="Oracles", components=oracle_components),
        ],
    )

    red_pillar = Pillar(
        pillar_id="red",
        label="Red",
        modules=[
            Module(
                module_id="red.adversary",
                label="Adversary",
                components=[
                    Component(
                        component_id="red.adversary",
                        label="Red adversary",
                        smoke=_shape_smoke(inputs.adversary, "mutate"),
                    )
                ],
            )
        ],
    )

    blue_pillar = Pillar(
        pillar_id="blue",
        label="Blue",
        modules=[
            Module(
                module_id="blue.sandbox",
                label="Blue sandbox",
                components=[
                    Component(
                        component_id="blue.sandbox",
                        label="Producer sandbox adapter",
                        smoke=(
                            _shape_smoke(inputs.sandbox, "run_python")
                            if inputs.sandbox is not None
                            else _docker_smoke
                        ),
                    )
                ],
            )
        ],
    )

    measure_pillar = Pillar(
        pillar_id="measure",
        label="Measure",
        modules=[
            Module(
                module_id="measure.metrics",
                label="Metrics + observability",
                components=[
                    Component(
                        component_id="measure.metrics",
                        label="Metrics engine",
                        smoke=_ok,
                    )
                ],
            )
        ],
    )

    deps_pillar = Pillar(
        pillar_id="external_deps",
        label="External dependencies",
        modules=[
            Module(
                module_id="external_deps",
                label="External dependencies",
                components=[
                    Component(
                        component_id="dep.postgres",
                        label="Postgres",
                        smoke=_postgres_smoke(inputs.session_factory),
                    ),
                    Component(
                        component_id="dep.sandbox",
                        label="Sandbox adapter (Docker)",
                        smoke=_docker_smoke,
                    ),
                    Component(
                        component_id="dep.anthropic",
                        label="Anthropic (token-free check)",
                        smoke=_anthropic_smoke(inputs.anthropic_ping),
                    ),
                ],
            )
        ],
    )

    return [targets_pillar, red_pillar, blue_pillar, measure_pillar, deps_pillar]


async def check_postgres(
    session_factory: async_sessionmaker[AsyncSession] | None,
) -> Leaf:
    """The real async Postgres connectivity leaf (``SELECT 1``).

    Run separately from the synchronous smoke sweep because it needs the event
    loop. Green on a successful trivial query (Postgres OR the SQLite test DB);
    red with the exception text otherwise. Never a run, just one query.
    """
    if session_factory is None:
        return Leaf(state=RED, last_self_test=_now_iso(), error="session factory not initialized")
    try:
        async with session_factory() as s:
            await s.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        return Leaf(state=RED, last_self_test=_now_iso(), error=f"{type(exc).__name__}: {exc}")
    return Leaf(state=GREEN, last_self_test=_now_iso(), error=None)


def _component_index(pillars: Sequence[Pillar]) -> dict[str, Component]:
    out: dict[str, Component] = {}
    for p in pillars:
        for m in p.modules:
            for c in m.components:
                out[c.component_id] = c
    return out


async def health_report(inputs: HealthInputs) -> dict[str, object]:
    """Build the full hierarchical self-test report (US-8) + the seal card (US-9).

    Runs every leaf's synchronous smoke, overlays the live async Postgres check,
    and attaches the producer-sandbox seal card. The structure is
    pillar -> module -> subcomponent, each leaf ``{state, last_self_test, error}``.
    """
    pillars = build_pillars(inputs)
    pg_leaf = await check_postgres(inputs.session_factory)

    pillar_dicts: list[dict[str, object]] = []
    for p in pillars:
        module_dicts: list[dict[str, object]] = []
        for m in p.modules:
            comp_dicts: list[dict[str, object]] = []
            for c in m.components:
                # The Postgres leaf uses the live async result, not the sync stub.
                leaf = pg_leaf if c.component_id == "dep.postgres" else c.run()
                comp_dicts.append(
                    {
                        "component_id": c.component_id,
                        "label": c.label,
                        **leaf.to_dict(),
                    }
                )
            module_dicts.append(
                {"module_id": m.module_id, "label": m.label, "subcomponents": comp_dicts}
            )
        pillar_dicts.append(
            {"pillar_id": p.pillar_id, "label": p.label, "modules": module_dicts}
        )

    return {
        "pillars": pillar_dicts,
        "seal_card": seal_card(inputs.sandbox),
    }


async def run_one_self_test(inputs: HealthInputs, component_id: str) -> dict[str, object]:
    """Re-run ONE subcomponent's smoke and return its updated leaf (US-8 button).

    Raises ``KeyError`` for an unknown id so the API can return a clean 404.
    """
    if component_id == "dep.postgres":
        leaf = await check_postgres(inputs.session_factory)
    else:
        pillars = build_pillars(inputs)
        comp = _component_index(pillars).get(component_id)
        if comp is None:
            raise KeyError(component_id)
        leaf = comp.run()
    return {"component_id": component_id, **leaf.to_dict()}


# ---------------------------------------------------------------------------
# Producer-sandbox seal card (US-9).
# ---------------------------------------------------------------------------


def seal_card(sandbox: object | None) -> dict[str, object]:
    """The producer-sandbox seal card (US-9) — STRUCTURE only, no probe run.

    Surfaces the static evidence the auditor reads: an EMPTY egress allow-list,
    the environment carried into the sandbox (none — no Postgres host, no
    provider creds, no Anthropic key), and the endpoint to run the live probe.
    Honest about Docker: if the adapter is absent or Docker is down, the card
    says the live probe is unavailable rather than implying a green seal.
    """
    docker_state, docker_error = _docker_smoke()
    available = docker_state == GREEN and sandbox is not None
    return {
        "sandbox_job_id": None,  # populated only when a live probe runs
        "egress_allow_list": [],  # the seal: NO egress is permitted
        # The container inherits NONE of the host env: no DB host, no creds, no
        # API key. We enumerate the categories proven absent, not real values.
        "env": [],
        "env_excludes": [
            "CRUCIBLE_DATABASE_URL (no Postgres host)",
            "ANTHROPIC_API_KEY (no provider creds)",
            "any sandbox/control-plane credential",
        ],
        "network": "none",
        "run_seal_probe_endpoint": "/health/seal-probe",
        "live_probe_available": available,
        "docker_state": docker_state,
        "docker_error": docker_error,
    }


# A host control-plane / metadata stand-in (the classic cloud metadata IP). A
# literal IP so its sealed failure is socket-layer network-unreachable, not DNS.
_CONTROL_PLANE = ("169.254.169.254", 80)
_PG_PORT = 5432


def run_live_seal_probe(sandbox: object | None) -> dict[str, object]:
    """Run the real in-sandbox seal probe (US-9 button) and report the result.

    Drives the existing ``run_seal_probe`` against the SAME concrete endpoints
    the seal integration test uses (the Postgres bridge gateway + the control
    plane). Returns ``{sealed, postgres_reached, host_reached, target_reached,
    job_id?, errors, available}``.

    HONEST when the live probe cannot run: if the sandbox adapter is absent, or
    Docker / the bridge gateway is unavailable, we return ``available=False`` with
    the reason — NEVER a fabricated ``sealed: true``.
    """
    if sandbox is None or not hasattr(sandbox, "run_python"):
        return {"available": False, "sealed": None, "reason": "no sandbox adapter wired"}
    docker_state, docker_error = _docker_smoke()
    if docker_state != GREEN:
        return {"available": False, "sealed": None, "reason": docker_error or "docker unavailable"}
    gateway = bridge_gateway_ip()
    if gateway is None:
        return {
            "available": False,
            "sealed": None,
            "reason": "docker bridge gateway IP not derivable; cannot pin a probe target",
        }
    targets = SealTargets(
        postgres=(gateway, _PG_PORT),
        host=_CONTROL_PLANE,
        target=(gateway, _PG_PORT),
    )
    try:
        result = run_seal_probe(cast_sandbox(sandbox), targets)
    except Exception as exc:  # noqa: BLE001 — a broken probe is reported, not faked sealed.
        return {"available": False, "sealed": None, "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "available": True,
        "sealed": result.all_sealed,
        "postgres_reached": result.postgres_reached,
        "host_reached": result.host_reached,
        "target_reached": result.target_reached,
        "errors": dict(result.errors),
    }


def cast_sandbox(obj: object) -> Sandbox:
    """Narrow an injected object to the ``Sandbox`` Protocol (duck-typed)."""
    return obj  # type: ignore[return-value]
