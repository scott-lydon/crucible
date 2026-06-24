"""Generic Python-source utilities.

The code-agent target and the held-out oracle both need to pull source out of
a model response and check that it parses. Modules cannot import each other
(coding-practices.md section 2), so these shared helpers live here, in the
layer both pillars are allowed to depend on.
"""

from __future__ import annotations

import ast


def extract_python_source(text: str) -> str:
    """Pull Python source out of a model response, fenced or not.

    Models are told to return bare source but sometimes wrap it in a ```python
    fence anyway, so this strips the first fenced block when present and
    otherwise returns the trimmed text.
    """
    stripped = text.strip()
    if "```" in stripped:
        block = stripped.split("```", 2)[1]
        if block.startswith("python"):
            block = block[len("python") :]
        return block.strip()
    return stripped


def is_valid_python(source: str) -> bool:
    """True when the source parses as Python."""
    try:
        ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return True
