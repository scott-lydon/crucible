"""Enforce Crucible's import boundaries (constitution hexagonal rule).

Rules (test_*.py files are exempt from all rules — tests may import freely):

1. modules/<x>/ may not import modules.<y> for x != y (hexagonal pillars stay
   decoupled). Intentional cross-imports are whitelisted in ALLOW.
2. No file under modules/ or orchestrator/ may import from examples.* — EXCEPT
   the composition root orchestrator/wiring.py (where a victim is plugged in).
3. No file under examples/ may import from modules.* or orchestrator.* — EXCEPT
   orchestrator.interfaces and shared.* (a victim may only see the Target
   Protocol + shared types).
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODULE_PATTERN = re.compile(r"^\s*(?:from|import)\s+modules\.([a-z_]+)", re.M)
HARNESS_FROM_EXAMPLES = re.compile(r"^\s*(?:from|import)\s+examples\b", re.M)
MODULES_IMPORT = re.compile(r"^\s*(?:from|import)\s+modules\b", re.M)
ORCHESTRATOR_IMPORT = re.compile(r"^\s*(?:from|import)\s+orchestrator(\.[a-z_.]+)?", re.M)

# Post-decoupling, the oracles/measure pillars no longer read the victim from
# modules.targets, so the old cross-import whitelist is obsolete.
ALLOW: set[tuple[str, str]] = set()

# The single composition root permitted to import a concrete victim.
COMPOSITION_ROOT = ROOT / "orchestrator" / "wiring.py"


def _check_module_cross_imports(path: pathlib.Path, text: str) -> list[str]:
    out: list[str] = []
    own = path.relative_to(ROOT / "modules").parts[0]
    for m in MODULE_PATTERN.finditer(text):
        imported = m.group(1)
        if imported != own and (own, imported) not in ALLOW:
            out.append(f"{path}: imports modules.{imported} (own pkg: {own})")
    return out


def _check_harness_no_examples(path: pathlib.Path, text: str) -> list[str]:
    if path.resolve() == COMPOSITION_ROOT:
        return []
    if HARNESS_FROM_EXAMPLES.search(text):
        return [f"{path}: imports examples.* (only orchestrator/wiring.py may)"]
    return []


def _check_examples_only_protocol(path: pathlib.Path, text: str) -> list[str]:
    out: list[str] = []
    for m in ORCHESTRATOR_IMPORT.finditer(text):
        suffix = m.group(1) or ""
        # allow exactly orchestrator.interfaces and its submodules
        if not (suffix == ".interfaces" or suffix.startswith(".interfaces.")):
            out.append(
                f"{path}: imports orchestrator{suffix} "
                "(examples may only import orchestrator.interfaces + shared.*)"
            )
    if MODULES_IMPORT.search(text):
        out.append(
            f"{path}: imports modules.* "
            "(examples may only import orchestrator.interfaces + shared.*)"
        )
    return out


def main() -> int:
    violations: list[str] = []

    for path in sorted((ROOT / "modules").rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        text = path.read_text()
        violations.extend(_check_module_cross_imports(path, text))
        violations.extend(_check_harness_no_examples(path, text))

    for path in sorted((ROOT / "orchestrator").rglob("*.py")):
        if path.name.startswith("test_"):
            continue
        text = path.read_text()
        violations.extend(_check_harness_no_examples(path, text))

    examples_dir = ROOT / "examples"
    if examples_dir.exists():
        for path in sorted(examples_dir.rglob("*.py")):
            if path.name.startswith("test_"):
                continue
            text = path.read_text()
            violations.extend(_check_examples_only_protocol(path, text))

    if violations:
        print("\n".join(violations))
        return 1
    print("module import discipline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
