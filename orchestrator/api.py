import dataclasses
import uuid
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from typing import AsyncIterator, cast

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from modules.measure.metrics import compute_run_metrics
from modules.targets.synth.constants import DETECTOR_THRESHOLD
from orchestrator.db import init_db as init_db  # re-export for tests
from orchestrator.db import session_factory
from orchestrator.interfaces import Adversary, Detector, Oracle
from orchestrator.loop import run_loop
from orchestrator.wiring import build_components
from shared.persistence import repo
from shared.persistence.models import RunRow
from shared.types import Transaction
from shared.types.enums import OracleKind


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    await init_db()
    yield


app = FastAPI(title="Crucible Fraud MVP v0", lifespan=_lifespan)


class LaunchRequest(BaseModel):
    n_rounds: int = Field(5, ge=1, le=50)
    batch_size: int = Field(200, ge=2, le=5000)
    seed: str = "seed-1"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs", status_code=201)
async def create_run(req: LaunchRequest) -> dict[str, str]:
    run_id = str(uuid.uuid4())
    sf = session_factory()
    async with sf() as s:
        s.add(
            RunRow(
                id=run_id,
                seed=req.seed,
                status="running",
                n_rounds=req.n_rounds,
                batch_size=req.batch_size,
                threshold=DETECTOR_THRESHOLD,
                params_json=req.model_dump(),
            )
        )
        await s.commit()
    comp = build_components(threshold=DETECTOR_THRESHOLD)
    # v0: run synchronously so the demo's numbers are ready on navigation
    await run_loop(
        sf,
        run_id=run_id,
        seed=req.seed,
        n_rounds=req.n_rounds,
        batch_size=req.batch_size,
        threshold=DETECTOR_THRESHOLD,
        detector=cast(Detector, comp["detector"]),
        adversary=cast(Adversary, comp["adversary"]),
        oracles=cast(Sequence[Oracle], comp["oracles"]),
        label_fn=cast(Callable[[Transaction], bool], comp["label_fn"]),
        generate_fn=cast(Callable[[str, int], list[Transaction]], comp["generate_fn"]),
    )
    return {"run_id": run_id}


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        run = await repo.get_run(s, run_id)
        if run is None:
            raise HTTPException(404, "run not found")
        verdicts = await repo.verdicts_for_run(s, run_id)
        return {
            "run_id": run.id,
            "status": run.status,
            "seed": run.seed,
            "n_rounds": run.n_rounds,
            "verdict_count": len(verdicts),
        }


@app.get("/runs/{run_id}/verdicts")
async def list_verdicts(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        verdicts = await repo.verdicts_for_run(s, run_id)
        return {"verdicts": [
            {"verdict_id": v.id, "round_id": v.round_id,
             "aggregate_pass": v.aggregate_pass, "fail_weight": v.fail_weight}
            for v in verdicts]}


@app.get("/runs/{run_id}/metrics")
async def get_metrics(run_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        m = await compute_run_metrics(s, run_id)
    if m is None:
        return {"status": "Not yet measured"}
    return {
        "per_round": [dataclasses.asdict(r) for r in m.per_round],
        "baseline_validation_detection": m.baseline_validation_detection,
        "gap": m.gap,
    }


@app.get("/runs/{run_id}/verdicts/{verdict_id}")
async def get_verdict(run_id: str, verdict_id: str) -> dict[str, object]:
    async with session_factory()() as s:
        votes = await repo.votes_for_verdict(s, verdict_id)
        if not votes:
            raise HTTPException(404, "verdict not found")
        return {
            "verdict_id": verdict_id,
            "run_id": run_id,
            "votes": [
                {
                    "oracle": v.oracle_kind,
                    "vote": v.vote,
                    "weight": v.weight,
                    "reason": v.reason,
                    "evidence": v.evidence_json,
                    "is_stub": v.oracle_kind == OracleKind.DIFFERENTIAL_STUB.value,
                    "is_mock": v.oracle_kind == OracleKind.LLM_JUDGE_MOCK.value,
                }
                for v in votes
            ],
        }
