"""Tests for ``PersistingLLMProvider``.

All offline/free: the inner provider is a deterministic ``MockProvider`` and the
DB is in-memory SQLite. Asserts that wrapping a provider records one ``llm_calls``
row per call (prompt/system/response/tokens/dollars captured) and that the inner
response is returned UNCHANGED with no extra model call.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.llm import MockProvider, PersistingLLMProvider
from shared.llm.base import LLMResponse
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence import repo
from shared.persistence.models import RunRow


@pytest.fixture
async def sf() -> async_sessionmaker[AsyncSession]:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await create_all(engine)
    factory = make_session_factory(engine)
    async with factory() as s:
        s.add(RunRow(id="run-1", seed="s", status="running", n_rounds=2,
                     batch_size=4, threshold=0.5, params_json={}))
        await s.commit()
    return factory


class _CountingProvider:
    """A MockProvider that also counts how many times complete() is called."""

    def __init__(self) -> None:
        self.calls = 0
        self._inner = MockProvider(text='{"vote": "fail"}', model="mock")

    def complete(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 4096, json_schema: object = None) -> LLMResponse:
        self.calls += 1
        # Return a response with real token/dollar fields to assert capture.
        return LLMResponse(text='{"vote": "fail"}', model="claude-opus-4-8",
                           input_tokens=1000, output_tokens=500, dollars=0.0175,
                           raw={"id": "resp_1"})


async def test_wrapping_records_one_row_per_call(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    inner = _CountingProvider()
    provider = PersistingLLMProvider(
        inner=inner, session_factory=sf, run_id="run-1", pillar="judge"
    )

    resp = provider.complete("the prompt", system="be terse")

    # Inner response returned UNCHANGED; exactly one inner call (no extra).
    assert resp.text == '{"vote": "fail"}'
    assert resp.dollars == 0.0175
    assert inner.calls == 1

    async with sf() as s:
        calls = await repo.llm_calls_for_run(s, "run-1")
    assert len(calls) == 1
    row = calls[0]
    assert row.pillar == "judge"
    assert row.model == "claude-opus-4-8"
    assert row.prompt == "the prompt"
    assert row.system == "be terse"
    assert row.input_tokens == 1000
    assert row.output_tokens == 500
    assert row.dollars == 0.0175
    assert row.raw_response is not None and "resp_1" in row.raw_response


async def test_two_calls_record_two_rows(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    provider = PersistingLLMProvider(
        inner=MockProvider(text="ok"), session_factory=sf, run_id="run-1",
        pillar="red",
    )
    provider.complete("a")
    provider.complete("b", system=None)

    async with sf() as s:
        calls = await repo.llm_calls_for_run(s, "run-1")
    assert len(calls) == 2
    assert {c.prompt for c in calls} == {"a", "b"}
    # MockProvider reports zero cost/tokens — captured honestly.
    assert all(c.dollars == 0.0 and c.input_tokens == 0 for c in calls)


async def test_get_llm_call_returns_full_record(
    sf: async_sessionmaker[AsyncSession],
) -> None:
    provider = PersistingLLMProvider(
        inner=_CountingProvider(), session_factory=sf, run_id="run-1",
        pillar="white_box",
    )
    provider.complete("inspect me", system="sys")
    async with sf() as s:
        calls = await repo.llm_calls_for_run(s, "run-1")
        full = await repo.get_llm_call(s, calls[0].id)
    assert full is not None
    assert full.prompt == "inspect me"
    assert full.system == "sys"
    assert full.pillar == "white_box"
