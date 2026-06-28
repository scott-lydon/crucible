"""PR #3 -> main port, Phase A (shared shape primitives). Verifies the three Phase A
goals against the real stack (real Postgres, real wired container, real API):

  A1  module value objects are frozen; the two stateless service classes named in the
      checklist are frozen dataclasses, the two state-bearing ones carry a written
      justification.
  A2  a missing target / oracle fails loud with a typed error that enumerates what IS
      registered, and the API surfaces it as a 422 (not a 500 "Internal server error").
  A3  the OracleVote serialization round trip is byte-identical, both as a unit and as
      proven by the live /attacks/{id}/replay endpoint over a real persisted verdict.
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from modules.blue.agent import FraudBlueAgent
from modules.blue.agent_blue import LLMAgentBlue
from modules.oracles.aggregator import vote_as_json, vote_from_json, votes_from_json
from modules.oracles.llm_judge.oracle import LLMJudgeOracle
from modules.red.llm_agent import LLMAgentRed
from orchestrator.errors import NoOracleRegisteredError, NoTargetRegisteredError
from orchestrator.wiring import build_container
from shared.types.core import Attack, AuditTrace, OracleVote, Verdict
from shared.types.enums import OracleKind
from tests.conftest import (
    FRAUD_SPEC_YAML,
    PGHOST,
    PGPASSWORD,
    PGPORT,
    PGUSER,
    TEST_DB,
)

# ----------------------------- A1 -----------------------------

def _is_frozen_dataclass(cls: type) -> bool:
    return dataclasses.is_dataclass(cls) and bool(cls.__dataclass_params__.frozen)  # type: ignore[attr-defined]


def test_a1_value_objects_are_frozen() -> None:
    # The actual module-output value objects: replay determinism depends on these.
    for cls in (OracleVote, Verdict, AuditTrace, Attack):
        assert _is_frozen_dataclass(cls), f"{cls.__name__} must be a frozen dataclass"


def test_a1_stateless_services_are_frozen_dataclasses() -> None:
    # The two checklist classes that carry no mutable state are frozen value objects.
    assert _is_frozen_dataclass(LLMJudgeOracle)
    assert _is_frozen_dataclass(FraudBlueAgent)


def test_a1_state_bearing_services_carry_written_justification() -> None:
    # The two state-bearing classes are the explicitly-allowed exception; each documents why.
    for cls in (LLMAgentRed, LLMAgentBlue):
        doc = cls.__doc__ or ""
        assert "A1 justification" in doc, f"{cls.__name__} must document the A1 exception"


def test_a1_frozen_instances_reject_mutation() -> None:
    judge = LLMJudgeOracle.__new__(LLMJudgeOracle)  # avoid constructing an LLM client
    with pytest.raises(dataclasses.FrozenInstanceError):
        judge._llm = "tamper"  # type: ignore[misc]


# ----------------------------- A2 -----------------------------

def test_a2_get_target_raises_typed_error_with_enumeration() -> None:
    container = build_container()
    with pytest.raises(NoTargetRegisteredError) as exc:
        container.get_target("nope")
    msg = str(exc.value)
    assert "Registered target types:" in msg
    assert "fraud" in msg  # a real registered kind is enumerated


def test_a2_get_oracles_raises_typed_error_with_enumeration() -> None:
    container = build_container()
    with pytest.raises(NoOracleRegisteredError) as exc:
        container.get_oracles("nope")
    assert "Registered:" in str(exc.value)


def test_a2_api_unknown_target_kind_is_422_not_500(client: TestClient) -> None:
    resp = client.post("/runs", json={"target_kind": "nope", "shape": "shape1_ml"})
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "Registered target types:" in detail
    assert "Internal server error" not in detail


# ----------------------------- A3 -----------------------------

def _sample_vote() -> OracleVote:
    return OracleVote(
        oracle=OracleKind.held_out, fired=True, weight=1.0,
        obligation="catch-fraud", observation="score 0.95 >= 0.5",
        reason="held-out fraud scored above threshold", seed="seed-1", dollars=0.0,
    )


def test_a3_vote_round_trip_is_byte_identical() -> None:
    v = _sample_vote()
    # inverse: deserialize(serialize(v)) reconstructs the exact value object
    assert vote_from_json(vote_as_json(v)) == v
    # idempotent serialization: re-serializing the rebuilt vote is byte-identical
    once = vote_as_json(v)
    assert vote_as_json(vote_from_json(once)) == once
    # the tuple form preserves order
    assert votes_from_json([vote_as_json(v), vote_as_json(v)]) == (v, v)


def _attack_id_with_verdict(run_id: str) -> str | None:
    async def _q() -> str | None:
        conn = await asyncpg.connect(
            host=PGHOST, port=PGPORT, user=PGUSER, password=PGPASSWORD, database=TEST_DB
        )
        try:
            row = await conn.fetchrow(
                "SELECT attack_id FROM verdicts WHERE run_id = $1 "
                "AND jsonb_array_length(votes) > 0 LIMIT 1",
                run_id,
            )
            return None if row is None else str(row["attack_id"])
        finally:
            await conn.close()

    return asyncio.run(_q())


def _poll_complete(client: TestClient, run_id: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        status = client.get(f"/runs/{run_id}").json()["status"]
        if status in ("complete", "failed"):
            return status
        time.sleep(0.1)
    return status


def test_a3_replay_endpoint_proves_votes_round_trip(client: TestClient) -> None:
    resp = client.post(
        "/runs",
        json={
            "target_kind": "fraud", "shape": "shape1_ml",
            "spec_yaml": FRAUD_SPEC_YAML, "budget_rounds": 2, "budget_dollars": 1.0,
        },
    )
    assert resp.status_code == 201, resp.text
    run_id = resp.json()["runId"]
    assert _poll_complete(client, run_id) == "complete"

    attack_id = _attack_id_with_verdict(run_id)
    assert attack_id is not None, "expected a fraud verdict with at least one vote"

    replay: dict[str, Any] = client.get(f"/attacks/{attack_id}/replay").json()
    # A3 governs the serialize/deserialize round trip of the persisted votes; that the
    # stored verdict's votes survive byte-identical is the audit-row replayer's guarantee.
    # (The separate "identical" field is the endpoint's pre-existing recompute comparison
    # and is not what A3 asserts.)
    assert replay["votesRoundTrip"] is True, replay
