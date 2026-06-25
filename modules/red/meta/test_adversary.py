"""Tests for the META-ATTACKER: the red writes + sandbox-runs its OWN mutation
code, with NO hand-coded attack surface.

Tiers:
  * FREE deterministic (MockProvider + in-process sandbox): proves the mechanism
    end-to-end with no Docker/network — the red runs LLM-written code and lands an
    objective evasion. Also asserts the module is target-agnostic (no declared
    movable_features; names no target fields).
  * Docker-GATED free (MockProvider + REAL LocalDockerSandbox): proves the
    untrusted mutation code actually runs in the locked-down container.
  * Key+Docker GATED live: a REAL Sonnet writes mutation code against a real
    Sparkov caught-fraud sample; reports HONESTLY what it wrote + whether it
    landed.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from contextlib import redirect_stdout
from dataclasses import dataclass

import pytest

from shared.llm.base import LLMResponse
from shared.sandbox.base import SandboxResult

from modules.red.meta.adversary import MetaRedAdversary


# --- An opaque sample dataclass (a stand-in target row; NOT a target import) --
@dataclass(frozen=True, slots=True)
class _Row:
    idx: int
    amt: float
    merchant_risk: float
    hour: int


# --- A MockProvider that returns ONE fixed mutation body --------------------
class _BodyProvider:
    """``LLMProvider`` returning a fixed ``mutate_body`` payload (deterministic)."""

    def __init__(self, mutate_body: str) -> None:
        payload = {"mutate_body": mutate_body, "rationale": "lower the score drivers"}
        import json

        self._text = json.dumps(payload)
        self.calls = 0

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text=self._text, model="mock", input_tokens=0, output_tokens=0, dollars=0.0
        )


# --- In-process sandbox (free, no Docker) — same exec shape as the blue tests -
class _InProcessSandbox:
    def run_python(
        self,
        code: str,
        *,
        timeout_s: float = 10.0,
        network: bool = False,
        stdin: str | None = None,
    ) -> SandboxResult:
        buf = io.StringIO()
        ns: dict[str, object] = {}
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(stdin or "")
            with redirect_stdout(buf):
                exec(code, ns)  # noqa: S102 — test-only fake sandbox
            return SandboxResult(
                stdout=buf.getvalue(), stderr="", exit_code=0,
                job_id="inproc", timed_out=False,
            )
        except Exception as exc:  # noqa: BLE001 — mimic the sandbox's failure capture
            return SandboxResult(
                stdout="", stderr=str(exc), exit_code=1,
                job_id="inproc", timed_out=False,
            )
        finally:
            sys.stdin = old_stdin


# A two-axis target: clears ONLY when amt is small AND merchant_risk is lowered.
def _score_two_axis(sample: object) -> float:
    amt = getattr(sample, "amt")
    risk = getattr(sample, "merchant_risk")
    return 0.1 if (amt <= 100.0 and risk <= 0.3) else 0.9


# Intent oracle: night-hour fraud regardless of amount (lowering amt/risk keeps it).
def _is_positive_night(sample: object) -> bool:
    return getattr(sample, "hour") in {0, 1, 2, 3}


# A mutation body the LLM "wrote": lower BOTH score drivers, leave hour alone.
_LOWER_TWO_AXIS = (
    "out = dict(row)\n"
    "out['amt'] = 50.0\n"
    "out['merchant_risk'] = 0.1\n"
    "return out\n"
)


def _meta(provider: _BodyProvider, sandbox: object, **kw: object) -> MetaRedAdversary:
    return MetaRedAdversary(
        provider=provider,
        score_fn=_score_two_axis,
        label_fn=_is_positive_night,
        threshold=0.5,
        sandbox=sandbox,  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )


# === FREE deterministic: the self-directed mechanism, no Docker =============


def test_red_writes_code_runs_it_and_lands_objective_evasion() -> None:
    """Given a caught sample + score_fn + intent oracle and NO movable_features,
    the red runs the LLM-WRITTEN mutation code in the sandbox and lands an evasion
    that is judged OBJECTIVELY (target clears AND intent preserved)."""
    provider = _BodyProvider(_LOWER_TWO_AXIS)
    sandbox = _InProcessSandbox()
    red = _meta(provider, sandbox)
    caught = _Row(idx=0, amt=1500.0, merchant_risk=0.9, hour=2)
    assert _score_two_axis(caught) >= 0.5  # genuinely caught to begin with

    out = red.mutate(caught, _score_two_axis(caught))

    assert out is not None
    # Objective landing: the RECONSTRUCTED sample clears the target...
    assert _score_two_axis(out) < 0.5
    # ...and the intent oracle still calls it positive.
    assert _is_positive_night(out) is True
    # The mutation was authored by the LLM and run in the sandbox (not in Python).
    assert red.last_mutate_body == _LOWER_TWO_AXIS
    assert provider.calls == 1
    # It is a true dataclass instance of the SAME type, rebuilt from the row.
    assert isinstance(out, _Row)
    assert out.amt == 50.0 and out.merchant_risk == 0.1
    assert out.hour == 2  # untouched field round-tripped through the sandbox


def test_red_was_given_no_hand_coded_attack_surface() -> None:
    """The red is constructed with NO movable_features and its prompt declares no
    fixed field/axis — it sees the whole row and decides. Proves target-agnostic
    self-direction at the API + prompt level."""
    import inspect

    from modules.red.meta import adversary as meta_mod

    # 1) The constructor exposes NO movable_features / attack-surface parameter.
    params = set(inspect.signature(MetaRedAdversary.__init__).parameters)
    assert "movable_features" not in params
    assert "attack_surface" not in params

    # 2) The system prompt frees the red to choose the whole strategy itself.
    system = meta_mod._SYSTEM.lower()
    assert "no prescribed field" in system
    assert "you decide the whole strategy" in system
    assert "def mutate(row" in system

    # 3) The module source names ZERO target-specific fields — fully generic.
    src = inspect.getsource(meta_mod)
    for target_field in (
        "amt", "merchant_risk", "cat_risk", "geo_distance_km", "velocity",
        "city_pop", "txn_index", "visible_tests", "held_out_tests",
    ):
        assert target_field not in src, f"module leaks target field {target_field!r}"


def test_sandbox_error_is_fed_back_then_a_repaired_body_lands() -> None:
    """A first body that raises is captured (NOT fatal) and fed back; the red's
    second body lands. Proves the write->run->verify->ITERATE loop and that
    untrusted failures never crash the loop."""

    class _TwoBodyProvider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(
            self, prompt: str, *, system: str | None = None,
            max_tokens: int = 4096, json_schema: Mapping[str, object] | None = None,
        ) -> LLMResponse:
            import json

            self.calls += 1
            if self.calls == 1:
                body = "raise ValueError('boom')\n"
            else:
                body = _LOWER_TWO_AXIS
                # The feedback from the failed run must be in the prompt.
                assert "FAILED to run" in prompt
                assert "boom" in prompt
            return LLMResponse(
                text=json.dumps({"mutate_body": body, "rationale": "r"}),
                model="mock", input_tokens=0, output_tokens=0, dollars=0.0,
            )

    provider = _TwoBodyProvider()
    red = MetaRedAdversary(
        provider=provider,
        score_fn=_score_two_axis,
        label_fn=_is_positive_night,
        threshold=0.5,
        sandbox=_InProcessSandbox(),
        max_iters=3,
    )
    caught = _Row(idx=0, amt=1500.0, merchant_risk=0.9, hour=2)
    out = red.mutate(caught, _score_two_axis(caught))
    assert out is not None
    assert provider.calls == 2
    assert _score_two_axis(out) < 0.5 and _is_positive_night(out) is True


def test_intent_breaking_mutation_does_not_land() -> None:
    """A body that clears the target but BREAKS the intent (changes hour out of the
    night window) is rejected by the objective verdict — not a landed evasion."""
    body = (
        "out = dict(row)\n"
        "out['amt'] = 50.0\n"
        "out['merchant_risk'] = 0.1\n"
        "out['hour'] = 12\n"  # clears target but flips the true label
        "return out\n"
    )
    red = MetaRedAdversary(
        provider=_BodyProvider(body),
        score_fn=_score_two_axis,
        label_fn=_is_positive_night,
        threshold=0.5,
        sandbox=_InProcessSandbox(),
        max_iters=1,
    )
    caught = _Row(idx=0, amt=1500.0, merchant_risk=0.9, hour=2)
    assert red.mutate(caught, _score_two_axis(caught)) is None


def test_budget_zero_returns_none_without_calling_provider() -> None:
    class _Boom:
        def complete(self, *a: object, **k: object) -> object:
            raise AssertionError("provider must not be called when budget is 0")

    red = MetaRedAdversary(
        provider=_Boom(),  # type: ignore[arg-type]
        score_fn=_score_two_axis,
        label_fn=_is_positive_night,
        threshold=0.5,
        sandbox=_InProcessSandbox(),
        max_calls=0,
    )
    caught = _Row(idx=0, amt=1500.0, merchant_risk=0.9, hour=2)
    assert red.mutate(caught, _score_two_axis(caught)) is None
    assert red.calls_made == 0


# === Docker-GATED free: the untrusted code runs in the REAL sandbox =========


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if docker is None:
        return False
    try:
        proc = subprocess.run(
            [docker, "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=30.0,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


@pytest.mark.skipif(not _docker_available(), reason="Docker daemon unavailable")
def test_red_runs_its_mutation_in_real_docker_sandbox() -> None:
    """The SAME mechanism, but the LLM-written mutation code runs in the locked-down
    LocalDockerSandbox (--network none, non-root, caps dropped). Proves untrusted
    code executes in the real sandbox, never in-process."""
    from shared.sandbox import LocalDockerSandbox

    provider = _BodyProvider(_LOWER_TWO_AXIS)
    red = _meta(provider, LocalDockerSandbox())
    caught = _Row(idx=0, amt=1500.0, merchant_risk=0.9, hour=2)
    out = red.mutate(caught, _score_two_axis(caught))
    assert out is not None
    assert _score_two_axis(out) < 0.5 and _is_positive_night(out) is True
    assert isinstance(out, _Row) and out.amt == 50.0


# === Key+Docker GATED live: a REAL Sonnet writes landing mutation code ======


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY")
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon unavailable")
def test_live_real_sonnet_writes_mutation_code_against_sparkov() -> None:
    """A REAL Sonnet 4.6 writes its OWN mutation code (no movable_features) against a
    real Sparkov caught-fraud sample; the code runs in Docker. Reports HONESTLY what
    it wrote + whether it landed (real targets/oracles may be robust — the FREE
    tests prove the mechanism regardless)."""
    from examples.targets import fraud_sparkov
    from modules.targets.local_model.adapter import LocalModelTarget
    from shared.llm.anthropic_api import AnthropicApiProvider
    from shared.sandbox import LocalDockerSandbox

    threshold = fraud_sparkov.DETECTOR_THRESHOLD
    detector = LocalModelTarget(
        model_path=fraud_sparkov.MODEL_PATH,
        feature_names=fraud_sparkov.DETECTOR_FEATURES,
    )
    batch = fraud_sparkov.generate_batch("meta-red-live", 300)
    caught = next(
        t for t in batch
        if fraud_sparkov.reference_is_fraud(t) and detector.score(t) >= threshold
    )
    red = MetaRedAdversary(
        provider=AnthropicApiProvider(model="claude-sonnet-4-6"),
        score_fn=detector.score,
        label_fn=fraud_sparkov.reference_is_fraud,  # intent = still fraud per reference
        threshold=threshold,
        sandbox=LocalDockerSandbox(),
        intent_description=(
            "Keep the transaction genuinely fraudulent — the reference fraud model "
            "must still classify it as fraud after your mutation."
        ),
        max_iters=2,
        max_calls=2,
    )
    import anthropic

    try:
        out = red.mutate(caught, detector.score(caught))
    except anthropic.APIStatusError as exc:
        # A present-but-unusable key (e.g. no credits / auth) is infra, not a code
        # failure — skip honestly rather than redden the suite, like the other
        # infra-gated live tests.
        pytest.skip(f"Anthropic API unavailable: {exc}")
    print(
        f"\n[LIVE meta-red] landed={out is not None} calls={red.calls_made}\n"
        f"--- mutation code the LLM wrote ---\n{red.last_mutate_body}"
    )
    if out is not None:
        # HONEST objective landing: target clears AND reference still says fraud.
        assert detector.score(out) < threshold
        assert fraud_sparkov.reference_is_fraud(out) is True
    assert red.calls_made <= 2
