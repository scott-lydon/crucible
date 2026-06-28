"""Runtime module-boundary audit (PR3 port F2).

The same architecture rule the CI script (scripts/check_module_imports.py) enforces, exposed
at runtime so a violation is operator-visible on the Admin Debug page rather than buried in
CI: no module under ``modules/<x>/`` may import another module's package ``modules.<y>``
(x != y). Modules talk only through ``orchestrator/interfaces`` and ``shared``.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_MODULES = _REPO / "modules"

# A debug-only injected offender (PR3 port F2): the operator arms it to see the badge flip
# red, then clears it. Also honored via CRUCIBLE_DEBUG_INJECT_BAD_IMPORT=1.
_inject_bad_import = False


def set_inject_bad_import(value: bool) -> None:
    global _inject_bad_import
    _inject_bad_import = value


def _owning_module(path: Path) -> str | None:
    parts = path.relative_to(_REPO).parts
    return parts[1] if len(parts) >= 2 and parts[0] == "modules" else None


def cross_module_offenders() -> list[str]:
    """Files under modules/<x>/ that import another module's package modules.<y> (x != y)."""
    offenders: list[str] = []
    for py in _MODULES.rglob("*.py"):
        owner = _owning_module(py)
        if owner is None:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            for name in names:
                segs = name.split(".")
                if len(segs) >= 2 and segs[0] == "modules" and segs[1] != owner:
                    offenders.append(
                        f"{py.relative_to(_REPO)} imports '{name}' "
                        f"(module '{owner}' may not import module '{segs[1]}')"
                    )
    return offenders


def import_audit() -> dict[str, object]:
    """The audit result for the dashboard badge: clean=True with no offenders, else the list."""
    offenders = cross_module_offenders()
    if _inject_bad_import or os.environ.get("CRUCIBLE_DEBUG_INJECT_BAD_IMPORT") == "1":
        offenders = [
            *offenders,
            "modules/red/llm_agent.py imports 'modules.blue.agent' "
            "(demo-injected cross-module import)",
        ]
    return {"clean": not offenders, "offenders": offenders}
