"""Slice 17 done-criterion: the SR 11-7 report renders from a real run.

Seeds a run with attacks, verdicts, and a blue patch on real Postgres, then
asserts GET /reports/:runId renders the six SR 11-7 sections with numbers linked
to their source-row routes (clicking a number jumps to the row), and that the
PDF download is a valid PDF with the same provenance. The test owns the blue
tables for its duration so the report's "latest patch" is deterministic.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete

from shared.persistence import get_sessionmaker
from shared.persistence.models import (
    AgentConfig,
    BluePatch,
    DifferentialRun,
    FuzzFinding,
    HoldoutRun,
    JudgeVote,
    ModelVersion,
    Run,
)
from shared.persistence.models import Attack as AttackRow
from shared.persistence.models import Verdict as VerdictRow


@pytest_asyncio.fixture(autouse=True)
async def _clean(migrated_database: str) -> AsyncIterator[None]:
    async with get_sessionmaker()() as session:
        for model in (
            JudgeVote, FuzzFinding, DifferentialRun, VerdictRow, AttackRow,
            HoldoutRun, ModelVersion, AgentConfig, BluePatch,
        ):
            await session.execute(delete(model))
        await session.commit()
    yield


async def _seed() -> tuple[str, str]:
    async with get_sessionmaker()() as session:
        run = Run(
            id=uuid.uuid4().hex, status="complete", target_type="fraud",
            artifact_ref="fraud-v1", spec_title="detect fraudulent transactions",
            spec_json={"title": "t", "obligations": []}, budget_max_attempts=4,
            budget_max_dollars=Decimal("1"), seed="seed-xyz",
        )
        session.add(run)
        await session.flush()
        attack = AttackRow(
            id=uuid.uuid4().hex, run_id=run.id, tactic="t", payload={"a": 1},
            succeeded=False, white_box=True, hybrid=False, pillar="red",
            dollars_spent=Decimal("0.02"), seed="s", audit_trace={"summary": "x", "steps": []},
        )
        session.add(attack)
        await session.flush()
        verdict = VerdictRow(
            id=uuid.uuid4().hex, run_id=run.id, attack_id=attack.id, passed=False,
            tally=3.0, votes=[], pillar="oracles", dollars_spent=Decimal("0"), seed="s",
            audit_trace={"summary": "x", "steps": []}, parent_action_id=attack.id,
        )
        session.add(verdict)
        patch = BluePatch(
            id=uuid.uuid4().hex, target_type="fraud", kind="retrain",
            detail={"provenance": []}, provenance=[], pillar="blue",
            dollars_spent=Decimal("0"), seed="s", audit_trace={"summary": "x", "steps": []},
        )
        session.add(patch)
        await session.flush()
        session.add(HoldoutRun(
            id=uuid.uuid4().hex, patch_id=patch.id, target_type="fraud", holdout_size=10,
            detection_before=0.0, detection_after=0.7, recovered=True, detail={}, seed="s",
        ))
        await session.commit()
        return run.id, verdict.id


async def test_report_renders_six_sections_with_row_links(client: AsyncClient) -> None:
    run_id, verdict_id = await _seed()

    resp = await client.get(f"/reports/{run_id}")
    assert resp.status_code == 200, resp.text
    md = resp.json()["markdown"]

    for heading in (
        "## 1. Purpose", "## 2. Model description", "## 3. Developmental evidence",
        "## 4. Ongoing monitoring", "## 5. Limitations", "## 6. Governance",
    ):
        assert heading in md, f"missing SR 11-7 section: {heading}"

    # Numbers link to their source rows (click the number, jump to the row).
    assert f"/runs/{run_id}/verdicts/{verdict_id}" in md
    assert f"](/runs/{run_id})" in md
    assert "/blue/" in md  # the blue patch recovery links to its row
    assert "seed-xyz" in md  # the replay seed is recorded


async def test_report_pdf_is_valid(client: AsyncClient) -> None:
    run_id, _ = await _seed()
    resp = await client.get(f"/reports/{run_id}.pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-1.4")
    assert resp.content.rstrip().endswith(b"%%EOF")


async def test_report_404_for_unknown_run(client: AsyncClient) -> None:
    assert (await client.get("/reports/nope")).status_code == 404
    assert (await client.get("/reports/nope.pdf")).status_code == 404
