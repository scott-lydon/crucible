"""The full-arc API test: a REAL Sparkov run end-to-end through POST /runs,
including the Option-B blue recovery arc, persisted — with ZERO real LLM calls.

The API builds components internally, so the test injects
``orchestrator.api.SPARKOV_TEST_OVERRIDES`` (mock providers + budget 0 on judge
and red, a scripted mock maker, and an in-process sandbox) so the loop runs
entirely on its FREE deterministic seams: the metamorphic mutator drives the red
loop, the mock judge abstains under budget 0, and the mock blue maker WRITES a
transform extracting the night hour from the raw timestamp. Nothing in this path
is mocked except the LLM + sandbox seams — the REAL LightGBM detector, REAL
Sparkov data, REAL mutator, and REAL engineered retraining all run.

Asserts the full red->verify->blue->recover story is persisted and exposed:
attacks + verdicts exist, a BlueRoundRow exists with detection_after >=
detection_before, GET /runs/{id}/blue returns it (with the iteration trail), and
/metrics returns the co-evolution numbers.

Skips (not fails) when the external Sparkov CSVs / artifact are absent.
"""

import contextlib
import io
import json
import sys
from collections.abc import AsyncGenerator, Mapping

import pytest
from httpx import ASGITransport, AsyncClient

import orchestrator.api as api
from examples.targets import fraud_sparkov
from orchestrator.api import app, init_db
from shared.llm import MockProvider
from shared.llm.base import LLMResponse
from shared.sandbox.base import SandboxResult


class _ScriptedMaker:
    """Returns the maker's hour transform on its call (zero real LLM)."""

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 4096,
        json_schema: Mapping[str, object] | None = None,
    ) -> LLMResponse:
        text = json.dumps({
            "feature_name": "night_hour",
            "rationale": "extract the hour from the raw timestamp",
            "engineer_src": "return float(str(row['trans_date_trans_time'])[11:13])",
        })
        return LLMResponse(text=text, model="mock", input_tokens=0, output_tokens=0, dollars=0.0)


class _InProcessSandbox:
    """Runs the wrapped transform locally (Docker boundary gated elsewhere)."""

    def run_python(
        self,
        code: str,
        *,
        timeout_s: float = 10.0,
        network: bool = False,
        stdin: str | None = None,
    ) -> SandboxResult:
        out = io.StringIO()
        saved_stdin = sys.stdin
        sys.stdin = io.StringIO(stdin or "")
        try:
            with contextlib.redirect_stdout(out):
                exec(code, {})  # noqa: S102 — wrapped harness code, test-only
        except Exception as exc:  # noqa: BLE001
            return SandboxResult(
                stdout=out.getvalue(), stderr=f"{type(exc).__name__}: {exc}",
                exit_code=1, job_id="t", timed_out=False,
            )
        finally:
            sys.stdin = saved_stdin
        return SandboxResult(
            stdout=out.getvalue(), stderr="", exit_code=0, job_id="t", timed_out=False,
        )

_DATA_READY = (
    fraud_sparkov.constants.TEST_CSV.exists()
    and fraud_sparkov.constants.TRAIN_CSV.exists()
    and fraud_sparkov.MODEL_PATH.exists()
    and fraud_sparkov.constants.CHECKSUM_PATH.exists()
)
_SKIP_REASON = (
    "Sparkov real CSVs / trained artifact missing (gitignored external inputs); "
    "run `python -m examples.targets.fraud_sparkov.train` after placing the data."
)

# Every LLM + sandbox seam neutralized: budget 0 on judge/red, a scripted mock
# maker, an in-process sandbox. ZERO real Sonnet/Opus calls, no Docker.
_OVERRIDES: dict[str, object] = {
    "judge_provider": MockProvider(
        text='{"per_obligation":[],"independent_finding":"fixture",'
        '"vote":"pass","reason":"fixture"}'
    ),
    "judge_max_calls": 0,
    "red_provider": MockProvider(
        text='{"moves":[{"feature":"amt","new_value":1.0}],"rationale":"x"}'
    ),
    "red_max_calls": 0,
    # white_box_max_calls=0 ⇒ the white-box self-test pass uses the deterministic
    # adversary (no real Opus calls), so this test is FULLY offline and never
    # depends on API credits. (It previously made real capped white-box calls.)
    "white_box_max_calls": 0,
    "blue_provider": _ScriptedMaker(),
    "blue_sandbox": _InProcessSandbox(),
}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    await init_db("sqlite+aiosqlite:///:memory:")
    api.SPARKOV_TEST_OVERRIDES = _OVERRIDES
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://t") as c:
            yield c
    finally:
        api.SPARKOV_TEST_OVERRIDES = None


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_full_sparkov_run_with_blue_via_api(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={
            "target": "sparkov",
            "rounds": 4,
            "batch_size": 80,
            "seed": "sparkov-full-arc",
            "run_blue": True,
        },
    )
    assert r.status_code == 201, r.text
    run_id = r.json()["run_id"]

    # Background task completes within the request lifecycle (ASGITransport).
    run = await client.get(f"/runs/{run_id}")
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "complete", run.json()

    # Verdicts persisted (the detector let attacked samples through -> oracles voted).
    verdicts = await client.get(f"/runs/{run_id}/verdicts")
    assert verdicts.status_code == 200
    assert len(verdicts.json()["verdicts"]) > 0

    # Co-evolution metrics surface for a sparkov run (generic shape holds).
    metrics = await client.get(f"/runs/{run_id}/metrics")
    assert metrics.status_code == 200
    body = metrics.json()
    assert "per_round" in body and body["per_round"]

    # The blue recovery arc was persisted and is exposed.
    blue = await client.get(f"/runs/{run_id}/blue")
    assert blue.status_code == 200, blue.text
    b = blue.json()
    assert b["n_holdout"] > 0
    assert b["detection_after"] >= b["detection_before"]
    # The maker engineered a named feature and recovered (Option B, no menu).
    assert b["features_added"] == ["night_hour"]
    assert b["detection_after"] > b["detection_before"]
    # The full iteration trail is persisted and exposed, carrying the maker's code.
    assert b["iteration_trail"]
    assert "trans_date_trans_time" in b["iteration_trail"][-1]["engineer_src"]


@pytest.mark.skipif(not _DATA_READY, reason=_SKIP_REASON)
async def test_blue_404_when_no_blue_run(client: AsyncClient) -> None:
    r = await client.post(
        "/runs",
        json={
            "target": "sparkov",
            "rounds": 2,
            "batch_size": 40,
            "seed": "sparkov-no-blue",
            "run_blue": False,
        },
    )
    assert r.status_code == 201
    run_id = r.json()["run_id"]
    blue = await client.get(f"/runs/{run_id}/blue")
    assert blue.status_code == 404
