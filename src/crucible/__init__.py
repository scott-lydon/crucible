"""Crucible — an automated AI red-team for AI agents you own.

Loop: Profile -> Attack -> Gate -> Fix -> Re-eval (held-out) -> Report.

The core is stdlib-only and runs fully offline against a built-in simulated
target, so the whole loop is testable and demoable without an LLM API key.
A real LLM (Anthropic) drops in behind the `crucible.llm.LLMClient` interface,
and real targets drop in behind `crucible.adapter.TargetAdapter`.
"""

__version__ = "0.1.0"
