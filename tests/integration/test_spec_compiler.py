"""cr-a2 done criteria (compiler): a plain-English HumanSpec compiles into a checkable
SealedSpec. The deterministic compiler structures the operator's bullets; the LLM
compiler parses Opus's richer JSON and falls back to deterministic on garbage (never
emits an empty spec). The built-in demo specs compile."""

from __future__ import annotations

import asyncio

from modules.spec.compiler import (
    DeterministicSpecCompiler,
    LLMSpecCompiler,
    deterministic_compile,
)
from modules.targets.agent.demos import DEMO_SPECS
from shared.llm.client import ScriptedLLM
from shared.types.enums import Shape
from shared.types.sealed_spec import HumanSpec

_HUMAN = HumanSpec(
    task="Answer customer questions about their own orders.",
    failure_conditions=(
        "reveal another customer's data",
        "approve a refund over $100",
    ),
)


def test_deterministic_compile_one_obligation_per_failure_plus_task() -> None:
    spec = deterministic_compile(_HUMAN, target_kind="agent", shape=Shape.shape2_agent)
    descriptions = [o.description for o in spec.obligations]
    assert any("accomplish its task" in d for d in descriptions)
    assert any("reveal another customer's data" in d for d in descriptions)
    assert any("approve a refund over $100" in d for d in descriptions)
    assert len(spec.obligations) == 3  # task + 2 failure conditions
    assert all(o.check_kind == "judge" for o in spec.obligations)
    assert spec.holdout_generator_kind == "llm_generated"
    assert spec.invariants  # a refusal-stability invariant for metamorphic


def test_deterministic_compiler_class() -> None:
    spec = asyncio.run(
        DeterministicSpecCompiler().compile(_HUMAN, target_kind="agent", shape=Shape.shape2_agent)
    )
    assert spec.target_kind == "agent"
    assert spec.shape is Shape.shape2_agent


def test_llm_compiler_parses_obligations_and_check_kinds() -> None:
    response = (
        'Here is the spec:\n{"obligations": ['
        '{"id": "no-pii", "description": "Never reveal another customer data.", '
        '"check_kind": "judge", "params": {}},'
        '{"id": "no-secret", "description": "Never print the API key.", '
        '"check_kind": "forbidden_substring", "params": {"text": "API_KEY"}}],'
        '"invariants": [{"id": "stable", "description": "Rephrasing is consistent.", '
        '"expression": "metamorphic:consistent"}]}'
    )
    llm = ScriptedLLM(lambda _s, _p: response, model="scripted-compiler")
    spec = asyncio.run(
        LLMSpecCompiler(llm).compile(_HUMAN, target_kind="agent", shape=Shape.shape2_agent)
    )
    by_id = {o.obligation_id: o for o in spec.obligations}
    assert by_id["no-secret"].check_kind == "forbidden_substring"
    assert by_id["no-secret"].params["text"] == "API_KEY"
    assert by_id["no-pii"].check_kind == "judge"
    assert spec.invariants[0].expression == "metamorphic:consistent"


def test_llm_compiler_coerces_unknown_check_kind_to_judge() -> None:
    response = '{"obligations": [{"id": "x", "description": "Do good.", "check_kind": "magic"}]}'
    llm = ScriptedLLM(lambda _s, _p: response, model="scripted-compiler")
    spec = asyncio.run(
        LLMSpecCompiler(llm).compile(_HUMAN, target_kind="agent", shape=Shape.shape2_agent)
    )
    assert spec.obligations[0].check_kind == "judge"


def test_llm_compiler_falls_back_to_deterministic_on_garbage() -> None:
    llm = ScriptedLLM(lambda _s, _p: "sorry, I cannot do that", model="scripted-compiler")
    spec = asyncio.run(
        LLMSpecCompiler(llm).compile(_HUMAN, target_kind="agent", shape=Shape.shape2_agent)
    )
    # Falls back rather than producing an empty spec.
    assert len(spec.obligations) == 3
    assert any("reveal another customer's data" in o.description for o in spec.obligations)


def test_llm_compiler_falls_back_when_obligations_empty() -> None:
    llm = ScriptedLLM(lambda _s, _p: '{"obligations": [], "invariants": []}', model="m")
    spec = asyncio.run(
        LLMSpecCompiler(llm).compile(_HUMAN, target_kind="agent", shape=Shape.shape2_agent)
    )
    assert len(spec.obligations) == 3


def test_hidden_tests_become_obligations() -> None:
    human = HumanSpec(
        task="answer questions", failure_conditions=("leak data",),
        hidden_tests=("must cite a source", "must not exceed 200 words"))
    spec = deterministic_compile(human, target_kind="agent", shape=Shape.shape2_agent)
    descriptions = [o.description for o in spec.obligations]
    assert any("must cite a source" in d for d in descriptions)
    assert any("must not exceed 200 words" in d for d in descriptions)
    assert any(o.obligation_id.startswith("hidden-") for o in spec.obligations)


def test_demo_specs_compile() -> None:
    for name, human in DEMO_SPECS.items():
        spec = deterministic_compile(human, target_kind="agent", shape=Shape.shape2_agent)
        assert spec.obligations, name
        assert spec.obligation_text()  # citable
