"""Persisting LLM client wrapper (US-2 trace cards, US-10 spend).

Wraps any `LlmClient` and records every call to the `llm_calls` table with the
run id, model, prompt, raw response, parsed output, token counts, and dollar
cost. The production run loop wires this per run so the dashboard's trace-card
Inspect view and the monthly-spend column read real data instead of an empty
table. The wrapper writes each row in its own short-lived session so it never
interferes with the run loop's own transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from shared.llm import LlmClient
from shared.llm.models import LlmModel, LlmResult
from shared.persistence import get_sessionmaker
from shared.persistence.models import LlmCall


@dataclass(frozen=True, slots=True)
class PersistingLlmClient:
    """An `LlmClient` that records each call to `llm_calls` after delegating."""

    base: LlmClient
    run_id: str
    pillar: str = "orchestrator"
    parent_action_id: str | None = None

    async def call(
        self,
        prompt: str,
        *,
        model: LlmModel,
        system: str | None = None,
    ) -> LlmResult:
        result = await self.base.call(prompt, model=model, system=system)
        try:
            async with get_sessionmaker()() as session:
                session.add(
                    LlmCall(
                        id=uuid.uuid4().hex,
                        run_id=self.run_id,
                        model=result.model.value,
                        prompt=prompt if system is None else (system + "\n\n" + prompt),
                        raw_response=result.text,
                        parsed_output=result.raw if isinstance(result.raw, dict) else {},
                        tokens_in=int(result.tokens_in or 0),
                        tokens_out=int(result.tokens_out or 0),
                        pillar=self.pillar,
                        dollars_spent=Decimal(str(getattr(result.dollars, "dollars", 0) or 0)),
                        seed=result.session_id or "",
                        parent_action_id=self.parent_action_id,
                    )
                )
                await session.commit()
        except Exception:  # persistence is observability, never fail the run on it
            pass
        return result
