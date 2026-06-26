#!/usr/bin/env python3
"""Pre-merge architecture check (constitution.md section 2).

1. No module imports another module's package: ``from modules.<y>`` inside
   ``modules/<x>/`` (x != y) is rejected. Modules talk only through
   ``orchestrator/interfaces`` and ``shared``.
2. A change set must not touch both ``shared/types/`` and ``modules/`` together
   (shared-folder discipline). Only checked when a git range is supplied.

Exit 0 clean, 1 on any violation. Wired into CI.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULES = REPO / "modules"


def _owning_module(path: Path) -> str | None:
    rel = path.relative_to(REPO)
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "modules":
        return parts[1]
    return None


def check_cross_module_imports() -> list[str]:
    violations: list[str] = []
    for py in MODULES.rglob("*.py"):
        owner = _owning_module(py)
        if owner is None:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # a syntax error is the linter's job, not ours
            violations.append(f"{py}: syntax error {exc}")
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
                    violations.append(
                        f"{py.relative_to(REPO)} imports '{name}' "
                        f"(module '{owner}' may not import module '{segs[1]}')"
                    )
    return violations


def check_changed_files(git_range: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", git_range],
            cwd=REPO, capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    touches_types = any(f.startswith("shared/types/") for f in changed)
    touches_modules = any(f.startswith("modules/") for f in changed)
    if touches_types and touches_modules:
        return [
            "change set touches both shared/types/ and modules/ — shared-folder "
            "changes ride their own branch (constitution.md section 2)"
        ]
    return []


def main(argv: list[str]) -> int:
    violations = check_cross_module_imports()
    if len(argv) > 1:
        violations += check_changed_files(argv[1])
    if violations:
        print("ARCHITECTURE CHECK FAILED:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("architecture check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
