"""Contract test: every `crucible ...` example inside skills/crucible/SKILL.md
must parse cleanly through the actual CLI's argparse, so the slash command's
documented surface and the CLI's argument shape can never drift apart.

The SKILL.md is the single source of truth describing the slash command's
contract; the CLI's `build_parser()` is the runtime authority. Co-locating them
in one repo is what makes this check possible (see commit history: this lives
in the same repo as `crucible/cli.py` and `pyproject.toml` so a CLI flag rename
in one PR has nowhere to hide). If you see this test fail, the SKILL.md and the
CLI disagree about a flag, a subcommand, or an argument shape, and one of them
must be updated in the same patch.

The test is intentionally over-permissive about placeholders (it substitutes
`<run_id>` and similar with safe dummy strings before parsing) and intentionally
strict about argument names (a typo in a flag name fails).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from crucible.cli import build_parser

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_PATH = _REPO_ROOT / "skills" / "crucible" / "SKILL.md"
# This test deliberately lives next to the CLI package (not under tests/) so it
# does not pick up tests/conftest.py's session-scope autouse Postgres setup;
# the contract check is pure parsing and has no database dependency.

# Captures every backtick-fenced `crucible ...` invocation in the SKILL.md.
# Matches the literal "crucible " prefix to skip "/crucible" slash command
# references (those describe the chat surface, not the shell surface).
_CLI_LINE = re.compile(r"`crucible ([^`\n]+)`")

# Placeholders the SKILL.md uses inside CLI examples; substituted with safe
# dummy values before parsing so argparse accepts them.
_PLACEHOLDER_SUBSTITUTIONS = {
    "<run_id>": "run_dummy",
    "<verdict_id>": "verdict_dummy",
    "<file>": "spec.yaml",
    "<spec>": "spec.yaml",
    "<n>": "3",
    "<d>": "5.0",
    "<target>": "fraud",
}


def _normalize(line: str) -> str:
    """Apply the documented placeholder substitutions so the example is
    runnable through argparse without invoking the underlying handler."""
    for placeholder, replacement in _PLACEHOLDER_SUBSTITUTIONS.items():
        line = line.replace(placeholder, replacement)
    return line.strip()


def _extract_cli_examples() -> list[tuple[int, str]]:
    """Return (line_number, normalized_invocation) tuples for every CLI example
    in skills/crucible/SKILL.md. The line number is surfaced in failure messages
    so a regression points the reader at the exact line to edit."""
    if not _SKILL_PATH.exists():
        pytest.skip(f"SKILL.md not found at {_SKILL_PATH}; this test runs only when "
                    f"the slash command source is checked into the repo (it should be).")
    examples: list[tuple[int, str]] = []
    for lineno, raw in enumerate(_SKILL_PATH.read_text().splitlines(), start=1):
        for match in _CLI_LINE.finditer(raw):
            examples.append((lineno, _normalize(match.group(1))))
    return examples


def test_skill_md_contains_at_least_one_cli_example() -> None:
    """Guards against a future refactor that strips all the examples from the
    SKILL.md (which would silently turn this test into a no-op)."""
    examples = _extract_cli_examples()
    assert examples, (
        f"No `crucible ...` examples found in {_SKILL_PATH}. The slash command's "
        f"documented surface lives in those examples; if they are gone, the "
        f"contract test cannot do its job. Restore them or rewrite this test."
    )


@pytest.mark.parametrize("example", _extract_cli_examples() or [(0, "")])
def test_skill_md_example_parses_through_cli(example: tuple[int, str]) -> None:
    """Each `crucible ...` example in the SKILL.md must parse without error
    through the real CLI's argparse. A failure here means the SKILL.md and the
    CLI's `build_parser()` disagree about a flag name, a subcommand name, or
    an argument's required-ness."""
    lineno, invocation = example
    if not invocation:
        pytest.skip("no examples found (separate guard test asserts presence)")
    parser = build_parser()
    argv = shlex.split(invocation)
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        pytest.fail(
            f"SKILL.md line {lineno}: `crucible {invocation}` does not parse through "
            f"the CLI's argparse (SystemExit={exc.code}). Either the SKILL.md example "
            f"is wrong (fix the example) or the CLI was changed without updating the "
            f"slash command's documented surface (fix the CLI back, or update the "
            f"SKILL.md to match the new shape, in the SAME patch as the CLI change)."
        )
