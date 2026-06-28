"""Packaging + CLI-surface regression tests for the merged crucible CLI.

Two independent guards that the dry-run goal loop does not exercise:

1. ``test_wheel_bundles_skill_md`` builds a real wheel and asserts the
   ``skills/crucible/SKILL.md`` resource lands inside it at that exact relative
   path. This is what lets ``crucible cowork install-skill`` read the SKILL.md
   from an installed wheel via importlib.resources without the repo on disk
   (pyproject.toml [tool.setuptools.package-data]). If the package-data
   declaration or the skills package layout drifts, the resource silently
   disappears from the wheel and only an end user hitting install-skill would
   notice; this test catches it at build time instead.

2. ``test_every_subcommand_help_parses`` walks every subparser exposed by
   ``crucible.cli.build_parser()`` (including nested ones like ``eligibility
   check`` and ``cowork install-skill``) and asserts ``python -m crucible
   <subcmd...> --help`` exits 0. This catches argparse construction drift in
   the subcommands the dry-run loop never runs (catalog, status, suitability,
   adapter, the focus subcommands, eval, demo, cowork): a duplicate option
   string or a broken argument definition makes build_parser() raise, which
   turns the ``--help`` exit code non-zero.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from crucible.cli import build_parser

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _subcommand_paths() -> list[list[str]]:
    """Every subcommand path reachable from build_parser(), parents and leaves.

    Returns e.g. [["run"], ["eligibility"], ["eligibility", "check"], ...].
    Parents are included because ``crucible eligibility --help`` must work too;
    leaves because that is where the real arguments live.
    """
    paths: list[list[str]] = []

    def walk(parser: argparse.ArgumentParser, prefix: list[str]) -> None:
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, subparser in action.choices.items():
                    paths.append([*prefix, name])
                    walk(subparser, [*prefix, name])

    walk(build_parser(), [])
    return paths


def test_wheel_bundles_skill_md(tmp_path: Path) -> None:
    """Build a wheel and assert skills/crucible/SKILL.md is inside it at the
    exact relative path importlib.resources will look for it under."""
    pytest.importorskip("build", reason="the [dev] extra installs `build`; needed to build a wheel")

    outdir = tmp_path / "dist"
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`python -m build --wheel` failed (exit {result.returncode}).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    wheels = list(outdir.glob("crucible-*.whl"))
    assert len(wheels) == 1, f"expected exactly one crucible wheel in {outdir}, found {wheels}"

    with zipfile.ZipFile(wheels[0]) as zf:
        names = zf.namelist()
    assert "skills/crucible/SKILL.md" in names, (
        "skills/crucible/SKILL.md is missing from the built wheel. The slash-command "
        "install handoff (`crucible cowork install-skill`) reads it via "
        "importlib.resources, so it must ship inside the wheel. Fix: verify "
        "[tool.setuptools.package-data] in pyproject.toml declares "
        '`"skills.crucible" = ["SKILL.md"]` and that skills/ and skills/crucible/ '
        f"are packages (have __init__.py). Wheel contents were: {sorted(names)}"
    )


@pytest.mark.parametrize("subcmd", _subcommand_paths(), ids=lambda p: " ".join(p))
def test_every_subcommand_help_parses(subcmd: list[str]) -> None:
    """`python -m crucible <subcmd...> --help` must exit 0 for every subparser.

    A failure means the subparser's argparse construction is broken (e.g. a
    duplicate option string or a bad argument definition), which is exactly the
    drift this guard exists to catch in the subcommands the dry-run loop never
    exercises."""
    result = subprocess.run(
        [sys.executable, "-m", "crucible", *subcmd, "--help"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"`crucible {' '.join(subcmd)} --help` exited {result.returncode} (expected 0).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
