"""Slice 11 done-criterion: the red agent's evasions surface in /catalog.

The search agent (driven by a sequenced LLM double over a fixture detector,
so no network) finds three distinct evasion tactics; each successful attack is
recorded in the strategy catalog on real Postgres; GET /catalog returns all
three. The append-only JSONL discovery log is also written. No mocks of the
database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from modules.red import RedSearchAgent, StrategyCatalog
from shared.llm import LlmModel, LlmResult
from shared.persistence import get_sessionmaker
from shared.persistence.models import StrategyCatalogEntry
from shared.types import (
    AttackBudget,
    AuditTrace,
    Money,
    ProbeResult,
    ProbeStatus,
    RunId,
    SealedSpec,
    TargetOutput,
    TargetType,
)


class _SequencedLlmClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def call(
        self, prompt: str, *, model: LlmModel, system: str | None = None
    ) -> LlmResult:
        text = self._responses.pop(0)
        return LlmResult(
            text=text,
            model=model,
            dollars=Money.of(0.01),
            tokens_in=0,
            tokens_out=0,
            session_id="seq",
            raw={"seq": True},
        )


@dataclass(frozen=True, slots=True)
class _FixtureDetector:
    score: float = 0.1
    target_type: TargetType = TargetType.FRAUD
    display_name: str = "Fixture Detector"
    description: str = "Test fixture detector for the strategy catalog test."
    artifact_ref: str = "fixture@v0"
    oracle_verified: bool = False

    async def submit(self, spec: SealedSpec, attack_input: dict[str, Any]) -> TargetOutput:
        return TargetOutput(
            output=attack_input, score=self.score, audit=AuditTrace(summary="fixture", steps=())
        )

    async def query_target(self, attack_input: dict[str, Any]) -> float:
        return self.score

    async def self_test(self) -> ProbeResult:
        return ProbeResult(status=ProbeStatus.GREEN, detail={"score": self.score})


_THREE_TACTICS = [
    '{"tactic": "round-amount", "payload": {"amount": 100}, "reasoning": "round looks normal"}',
    '{"tactic": "micro-charge", "payload": {"amount": 3}, "reasoning": "tiny charges fly under"}',
    '{"tactic": "trusted-merchant", "payload": {"m": "coffee"}, "reasoning": "trusted seller"}',
]


def _spec() -> SealedSpec:
    return SealedSpec.from_payload(
        {
            "title": "evade the detector",
            "obligations": [{"id": "o1", "description": "the transaction is fraudulent"}],
        }
    )


@pytest_asyncio.fixture(autouse=True)
async def _clean_catalog(migrated_database: str) -> AsyncIterator[None]:
    """Truncate the strategy catalog before each test.

    The table is keyed by (tactic, target_type), not by run, so rows would
    otherwise accumulate across tests and across pytest runs and make the reuse
    counts non-deterministic.
    """
    async with get_sessionmaker()() as session:
        await session.execute(delete(StrategyCatalogEntry))
        await session.commit()
    yield


async def test_three_evasions_surface_in_catalog(client: AsyncClient, tmp_path: Path) -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient(_THREE_TACTICS))
    jsonl = tmp_path / "strategy_catalog.jsonl"

    attacks = await agent.search(
        _spec(),
        _FixtureDetector(),
        AttackBudget(max_attempts=3, max_dollars=Money.of(1.0)),
        RunId.new(),
        white_box=False,
    )
    succeeded = [a for a in attacks if a.succeeded]
    assert len(succeeded) == 3

    async with get_sessionmaker()() as session:
        cat = StrategyCatalog(session=session, jsonl_path=jsonl)
        for attack in succeeded:
            await cat.record_success(attack, TargetType.FRAUD)
        await session.commit()

    resp = await client.get("/catalog")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    tactics = {row["tactic"] for row in rows}
    assert {"round-amount", "micro-charge", "trusted-merchant"} <= tactics

    row = next(r for r in rows if r["tactic"] == "round-amount")
    assert row["target_type"] == "fraud"
    assert row["reuse_count"] == 1
    assert row["avg_dollars_to_succeed"] == 0.01
    assert "amount" in row["prompt_fragment"]
    assert row["discovery_audit"]["steps"]  # the discovery trace is present

    assert len(jsonl.read_text(encoding="utf-8").splitlines()) == 3


async def test_rediscovery_increments_reuse_count(client: AsyncClient, tmp_path: Path) -> None:
    agent = RedSearchAgent(llm=_SequencedLlmClient([_THREE_TACTICS[0], _THREE_TACTICS[0]]))
    attacks = await agent.search(
        _spec(),
        _FixtureDetector(),
        AttackBudget(max_attempts=2, max_dollars=Money.of(1.0)),
        RunId.new(),
        white_box=False,
    )

    async with get_sessionmaker()() as session:
        cat = StrategyCatalog(session=session, jsonl_path=tmp_path / "c.jsonl")
        for attack in attacks:
            await cat.record_success(attack, TargetType.FRAUD)
        await session.commit()
        entries = await cat.entries(TargetType.FRAUD)

    same = [e for e in entries if e.tactic == "round-amount"]
    assert len(same) == 1
    assert same[0].reuse_count == 2
    # Two discoveries at 0.01 each, averaged back to 0.01 per success.
    assert same[0].avg_dollars_to_succeed == 0.01
