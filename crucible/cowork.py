"""Cowork integration: install the /crucible SKILL.md into the user's Claude
skills directory so Cowork (or Claude Code) picks it up.

The SKILL.md ships as package data inside `skills/crucible/`; this module reads
it via importlib.resources so it works from an installed wheel without needing
the source repo on disk. This is the install-time hand-off for the
[slash-command] extra (see pyproject.toml): `pip install crucible[slash-command]`
puts the file in the wheel; `crucible cowork install-skill` writes it to disk.
"""

from __future__ import annotations

import argparse
import importlib.resources
import shutil
from pathlib import Path

_DEFAULT_DEST = Path.home() / ".claude" / "skills" / "crucible" / "SKILL.md"
_SKILL_PACKAGE = "skills.crucible"
_SKILL_RESOURCE = "SKILL.md"


class SkillNotFoundError(RuntimeError):
    """The bundled SKILL.md is missing from the wheel. Surfaces a precise
    diagnostic when packaging is misconfigured rather than a generic ImportError."""


def bundled_skill_path() -> Path:
    """Return the on-disk path of the bundled SKILL.md (extracted from the wheel
    when needed). Raises SkillNotFoundError if the package data is missing,
    which means the wheel was built without the [slash-command] extra's data
    declaration in pyproject.toml."""
    try:
        resource = importlib.resources.files(_SKILL_PACKAGE).joinpath(_SKILL_RESOURCE)
    except (ModuleNotFoundError, FileNotFoundError) as exc:
        raise SkillNotFoundError(
            f"Bundled {_SKILL_PACKAGE}/{_SKILL_RESOURCE} not found in the installed "
            f"package. Fix: reinstall with `pip install crucible[slash-command]` so "
            f"the SKILL.md is included as package data."
        ) from exc
    if not resource.is_file():
        raise SkillNotFoundError(
            f"Bundled {_SKILL_PACKAGE}/{_SKILL_RESOURCE} resolved to a non-file "
            f"({resource}). Fix: verify [tool.setuptools.package-data] in "
            f"pyproject.toml includes `\"skills.crucible\" = [\"SKILL.md\"]`."
        )
    return Path(str(resource))


def install_skill(dest: Path = _DEFAULT_DEST, *, force: bool = False) -> Path:
    """Copy the bundled SKILL.md to `dest` (default ~/.claude/skills/crucible/SKILL.md).

    Refuses to overwrite an existing file without `force=True` so a user who has
    edited the file locally does not lose changes silently. Returns the final
    destination path so callers can print it to the user.
    """
    src = bundled_skill_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        raise FileExistsError(
            f"{dest} already exists. Pass --force to overwrite, or move the existing "
            f"file aside first. Existing file may contain local edits the install "
            f"would otherwise discard."
        )
    shutil.copyfile(src, dest)
    return dest


def cmd_cowork_install_skill(args: argparse.Namespace) -> int:
    """`crucible cowork install-skill [--dest PATH] [--force]` dispatcher."""
    dest = Path(args.dest).expanduser() if args.dest else _DEFAULT_DEST
    try:
        written = install_skill(dest, force=bool(args.force))
    except SkillNotFoundError as exc:
        print(f"error: {exc}")
        return 1
    except FileExistsError as exc:
        print(f"error: {exc}")
        return 2
    print(f"installed: {written}")
    return 0
