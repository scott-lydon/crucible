"""Slice 3 done-criterion: the code agent produces ast-parseable Python.

Opt-in live test (CRUCIBLE_RUN_LLM_TESTS=1 plus `claude` on PATH), since it
calls the real CLI. No mock: this is the real producer generating real code.
"""

from __future__ import annotations

import ast
import os
import shutil

import pytest

from modules.targets.code_agent import CodeAgentTarget
from shared.llm import ClaudeCliClient
from shared.types import SealedSpec

_should_run = os.environ.get("CRUCIBLE_RUN_LLM_TESTS") == "1" and shutil.which("claude")

pytestmark = pytest.mark.skipif(
    not _should_run,
    reason="set CRUCIBLE_RUN_LLM_TESTS=1 and have the claude CLI on PATH to run",
)


async def test_produces_ast_parseable_python() -> None:
    spec = SealedSpec.from_payload(
        {
            "title": "add two integers",
            "obligations": [
                {"id": "o1", "description": "define a function add(a, b) that returns a + b"}
            ],
        }
    )
    out = await CodeAgentTarget(llm=ClaudeCliClient()).submit(spec, {"signature": "add(a, b)"})
    ast.parse(out.output)  # raises SyntaxError if the producer emitted invalid code
    assert out.score == 1.0
