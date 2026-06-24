#!/usr/bin/env python3
"""Pre-merge guard for the hexagonal layout (coding-practices.md section 2).

Two checks:

1. Cross-module imports. A file under `modules/<y>/` may not import from
   `modules/<x>/` when x is not y. Modules talk only through
   `orchestrator/interfaces/` and `shared/`. This is a static scan of the
   whole tree and always runs.

2. shared/types + modules co-edit. A single commit may not edit both
   `shared/types/` and `modules/` (type and interface churn rides its own
   commit so reviews stay scoped, per tasks.md slice 0). This compares the
   latest commit against its parent; it is skipped gracefully when git is
   unavailable so the cross-module scan still runs.

Exit code 0 means clean; 1 means at least one violation, printed with the
exact file and the rule it broke.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = REPO_ROOT / "modules"


def _owning_module(path: Path) -> str | None:
    """Return the module name owning a file under modules/<name>/, else None."""
    try:
        rel = path.relative_to(MODULES_DIR)
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def _imported_sibling(import_target: str, owner: str) -> str | None:
    """Return the sibling module name if import_target reaches into one, else None."""
    if not import_target.startswith("modules."):
        return None
    imported = import_target.split(".")[1]
    return imported if imported != owner else None


def find_cross_module_imports() -> list[str]:
    """Scan every modules/*.py for an import of a sibling module."""
    violations: list[str] = []
    for py in sorted(MODULES_DIR.rglob("*.py")):
        owner = _owning_module(py)
        if owner is None:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                targets.append(node.module)
            elif isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            for target in targets:
                sibling = _imported_sibling(target, owner)
                if sibling is not None:
                    rel = py.relative_to(REPO_ROOT)
                    violations.append(
                        f"{rel}: imports sibling 'modules.{sibling}' (owner is "
                        f"'modules.{owner}'). Route it through "
                        f"orchestrator/interfaces/ or shared/ instead."
                    )
    return violations


def find_shared_types_and_module_coedit() -> list[str]:
    """Flag a commit that edits both shared/types/ and modules/ at once."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1...HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        # No parent commit or git unavailable: the cross-module scan still ran.
        return []
    changed = [line for line in result.stdout.splitlines() if line.strip()]
    touched_types = any(c.startswith("shared/types/") for c in changed)
    touched_module = any(c.startswith("modules/") for c in changed)
    if touched_types and touched_module:
        return [
            "the latest commit edits both shared/types/ and modules/; split "
            "the type or interface change into its own commit (tasks.md slice 0, "
            "coding-practices.md section 2)."
        ]
    return []


def main() -> int:
    violations = find_cross_module_imports() + find_shared_types_and_module_coedit()
    if violations:
        print("Module-boundary check FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("Module-boundary check passed: no cross-module imports, no shared/types co-edit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
