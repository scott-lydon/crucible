"""Code-agent target (Shape 2): produces Python source for a sealed spec."""

from __future__ import annotations

from shared.source import extract_python_source, is_valid_python

from .code_agent_target import CodeAgentTarget

__all__ = ["CodeAgentTarget", "extract_python_source", "is_valid_python"]
