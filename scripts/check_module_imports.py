"""Fail if a modules/<x>/ file imports modules.<y> (x != y) — constitution hexagonal rule.

Whitelisted cross-imports (intentional in v0): oracles and measure may read the
sealed ground-truth rule/constants from targets. Test files are exempt.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PATTERN = re.compile(r"^\s*from\s+modules\.([a-z_]+)", re.M)
ALLOW: set[tuple[str, str]] = {("oracles", "targets"), ("measure", "targets")}


def main() -> int:
    violations: list[str] = []
    for path in sorted((ROOT / "modules").rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        own = path.relative_to(ROOT / "modules").parts[0]
        for m in PATTERN.finditer(path.read_text()):
            imported = m.group(1)
            if imported != own and (own, imported) not in ALLOW:
                violations.append(f"{path}: imports modules.{imported} (own pkg: {own})")
    if violations:
        print("\n".join(violations))
        return 1
    print("module import discipline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
