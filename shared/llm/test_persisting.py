"""Tests for ``PersistingLLMProvider``.

All offline/free: the inner provider is a deterministic ``MockProvider`` and the
DB is a temp-file SQLite. Asserts that wrapping a provider records one
``llm_calls`` row per call (prompt/system/response/tokens/dollars captured) and
that the inner response is returned UNCHANGED with no extra model call.

The write path is the LOOP-SAFE sync writer (no async engine): the provider takes
a ``db_url`` and inserts through a blocking sync engine. We use a temp FILE SQLite
(not ``:memory:``) so the async setup connection and the sync write connection see
the SAME database — the cross-connection share that ``:memory:`` can't provide.
"""

import pathlib
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.llm import MockProvider, PersistingLLMProvider
from shared.llm.base import LLMResponse
from shared.persistence import create_all, make_engine, make_session_factory
from shared.persistence import repo
from shared.persistence.models import RunRow


class _Wired:
    """The async read factory plus the async DB URL the writer translates."""

    def __init__(self, sf: async_sessionmaker[AsyncSession], db_url: str) -> None:
        self.sf = sf
        self.db_url = db_url


@pytest.fixture
async def wired(tmp_path: pathlib.Path) -> AsyncIterator[_Wired]:
    db_file = tmp_path / "persist.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = make_engine(db_url)
    await create_all(engine)
    factory = make_session_factory(engine)
    async with factory() as s:
        s.add(RunRow(id="run-1", seed="s", status="running", n_rounds=2,
                     batch_size=4, threshold=0.5, params_json={}))
        await s.commit()
    yield _Wired(factory, db_url)
    await engine.dispose()


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


async def test_wrapping_records_one_row_per_call(wired: _Wired) -> None:
    inner = _CountingProvider()
    provider = PersistingLLMProvider(
        inner=inner, db_url=wired.db_url, run_id="run-1", pillar="judge"
    )

    resp = provider.complete("the prompt", system="be terse")

    # Inner response returned UNCHANGED; exactly one inner call (no extra).
    assert resp.text == '{"vote": "fail"}'
    assert resp.dollars == 0.0175
    assert inner.calls == 1

    async with wired.sf() as s:
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


async def test_two_calls_record_two_rows(wired: _Wired) -> None:
    provider = PersistingLLMProvider(
        inner=MockProvider(text="ok"), db_url=wired.db_url, run_id="run-1",
        pillar="red",
    )
    provider.complete("a")
    provider.complete("b", system=None)

    async with wired.sf() as s:
        calls = await repo.llm_calls_for_run(s, "run-1")
    assert len(calls) == 2
    assert {c.prompt for c in calls} == {"a", "b"}
    # MockProvider reports zero cost/tokens — captured honestly.
    assert all(c.dollars == 0.0 and c.input_tokens == 0 for c in calls)


async def test_get_llm_call_returns_full_record(wired: _Wired) -> None:
    provider = PersistingLLMProvider(
        inner=_CountingProvider(), db_url=wired.db_url, run_id="run-1",
        pillar="white_box",
    )
    provider.complete("inspect me", system="sys")
    async with wired.sf() as s:
        calls = await repo.llm_calls_for_run(s, "run-1")
        full = await repo.get_llm_call(s, calls[0].id)
    assert full is not None
    assert full.prompt == "inspect me"
    assert full.system == "sys"
    assert full.pillar == "white_box"
