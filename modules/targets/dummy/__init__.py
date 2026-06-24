"""Dummy target: a canned Target implementation for the loop smoke test.

Exists only so the orchestrator spine (wiring, submit, persistence) can be
exercised before a real model or LLM target lands (slices 2 and 3). It is the
DUMMY target type and is never wired into a production run.
"""

from __future__ import annotations

from .dummy_target import DummyTarget

__all__ = ["DummyTarget"]
