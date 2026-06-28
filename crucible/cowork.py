"""Cowork integration: install the /crucible SKILL.md into the user's Claude
skills directory so Cowork (or Claude Code) picks it up.

The SKILL.md ships as package data inside `skills/crucible/`; this module reads
it via importlib.resources so it works from an installed wheel without needing
the source repo on disk. This is the install-time hand-off for the
[slash-command] extra (see pyproject.toml): `pip install crucible[slash-command]`
puts the file in the wheel; `crucible cowork install-skill` writes it to disk.
"""

# Design decision: copy vs symlink for ~/.claude/skills/crucible/SKILL.md.
#
# Two ways to put the bundled SKILL.md where Claude reads it, chosen by the
# operator with `--mode {copy,symlink}` (default copy):
#
# (a) Copy (default). `install-skill` writes a standalone file. Pro: survives a
#     package uninstall, never dangles, works identically on every OS. Con: a
#     drift window opens on every wheel upgrade, because the on-disk copy keeps
#     the old text until the operator re-runs `install-skill --force`. We close
#     that window by detecting drift: copy mode compares the on-disk file to the
#     bundled one and refuses to overwrite a differing file without --force, so a
#     stale-after-upgrade copy and a hand-edited local copy are both surfaced
#     loudly (skill_status reports "drifted") instead of silently clobbered.
#
# (b) Symlink (opt-in). `install-skill --mode symlink` links the destination at
#     the bundled path, so a wheel upgrade is reflected with zero drift and no
#     re-run. Con: symlinks need Developer Mode or admin rights on Windows and
#     break if the package is moved or uninstalled, so it is not the safe
#     default. It assumes a normal (unzipped) install where the resource path is
#     stable; a zipimport install has no stable target to point at.
#
# Default copy: safe and portable. Symlink for operators who want auto-refresh.

from __future__ import annotations

import argparse
import filecmp
import importlib.resources
import os
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


def skill_status(dest: Path = _DEFAULT_DEST, *, src: Path | None = None) -> str:
    """Report the destination's relationship to the bundled SKILL.md, so the
    operator can see drift instead of guessing. One of:

    - ``"missing"``     — nothing at ``dest`` yet.
    - ``"up-to-date"``  — a copy whose bytes equal the bundled file.
    - ``"drifted"``     — a copy whose bytes differ (a stale-after-upgrade copy
      or a hand-edited local file); needs ``--force`` to overwrite in copy mode.
    - ``"symlink-ok"``  — a symlink that resolves to the bundled file.
    - ``"symlink-stale"`` — a symlink that resolves somewhere other than the
      bundled file (e.g. a previous install pointed at an old location).
    """
    src = src if src is not None else bundled_skill_path()
    if not dest.exists() and not dest.is_symlink():
        return "missing"
    if dest.is_symlink():
        return "symlink-ok" if os.path.realpath(dest) == os.path.realpath(src) else "symlink-stale"
    return "up-to-date" if filecmp.cmp(dest, src, shallow=False) else "drifted"


def install_skill(
    dest: Path = _DEFAULT_DEST, *, mode: str = "copy", force: bool = False,
    src: Path | None = None,
) -> Path:
    """Install the bundled SKILL.md to ``dest`` (default
    ~/.claude/skills/crucible/SKILL.md) as a copy (``mode="copy"``, the default)
    or a symlink (``mode="symlink"``). See the module-top design note for the
    copy-vs-symlink trade-offs.

    Copy mode refuses to overwrite a destination whose content differs from the
    bundle without ``force=True``, so a stale-after-upgrade copy or a hand-edited
    local file is surfaced rather than silently clobbered; an identical copy is a
    no-op. Symlink mode refuses to replace a real file (or a symlink pointing
    elsewhere) without ``force=True``. Returns the destination path.

    ``src`` overrides the bundled-source path (defaults to ``bundled_skill_path()``);
    it is a real-file seam for tests and is not a stub.
    """
    if mode not in ("copy", "symlink"):
        raise ValueError(f"unknown install mode {mode!r}; expected 'copy' or 'symlink'")
    src = src if src is not None else bundled_skill_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    status = skill_status(dest, src=src)

    if mode == "copy":
        if status == "up-to-date":
            return dest
        if status != "missing" and not force:
            raise FileExistsError(
                f"{dest} differs from the bundled SKILL.md ({status}). Either you "
                f"edited it locally or a wheel upgrade changed the bundle. Pass "
                f"--force to overwrite with the bundled copy, or move the file aside."
            )
        # An existing symlink must be removed before copyfile (which would follow it).
        if dest.is_symlink() or dest.exists():
            dest.unlink()
        shutil.copyfile(src, dest)
        return dest

    # mode == "symlink"
    if status == "symlink-ok":
        return dest
    if status != "missing" and not force:
        raise FileExistsError(
            f"{dest} already exists ({status}); refusing to replace it with a symlink. "
            f"Pass --force to replace it, or move the file aside."
        )
    if dest.is_symlink() or dest.exists():
        dest.unlink()
    dest.symlink_to(os.path.realpath(src))
    return dest


def cmd_cowork_install_skill(args: argparse.Namespace) -> int:
    """`crucible cowork install-skill [--dest PATH] [--mode copy|symlink] [--force]`."""
    dest = Path(args.dest).expanduser() if args.dest else _DEFAULT_DEST
    mode = getattr(args, "mode", "copy")
    try:
        written = install_skill(dest, mode=mode, force=bool(args.force))
    except SkillNotFoundError as exc:
        print(f"error: {exc}")
        return 1
    except FileExistsError as exc:
        print(f"error: {exc}")
        return 2
    print(f"installed ({mode}): {written}")
    return 0
