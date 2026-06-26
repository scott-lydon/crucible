"""The spec compiler: turns an operator's plain-English ``HumanSpec`` (what the
agent is for + what counts as failure) into the checkable ``SealedSpec`` the oracle
ensemble grades against (plan.md section 5). A deterministic compiler structures the
operator's own bullets; the LLM compiler (Opus) additionally infers obligations,
invariants, and per-obligation check kinds."""

from __future__ import annotations

from modules.spec.compiler import (
    DeterministicSpecCompiler,
    LLMSpecCompiler,
    SpecCompiler,
    deterministic_compile,
)

__all__ = [
    "DeterministicSpecCompiler",
    "LLMSpecCompiler",
    "SpecCompiler",
    "deterministic_compile",
]
