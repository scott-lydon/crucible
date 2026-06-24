"""Code-agent target (Shape 2): produces Python source for a sealed spec."""

from __future__ import annotations

from .code_agent_target import CodeAgentTarget, extract_python_source, is_valid_python

__all__ = ["CodeAgentTarget", "extract_python_source", "is_valid_python"]
