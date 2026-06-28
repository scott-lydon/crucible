"""Tests for `crucible cowork install-skill` copy vs symlink modes.

Every case uses real files on a real temp filesystem (pytest's tmp_path) and the
real install_skill / skill_status code paths. `install_skill(..., src=...)`
injects a real bundled-source file so a test can simulate a wheel upgrade by
changing that file's bytes; it is a real file, not a stub.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from crucible.cowork import bundled_skill_path, install_skill, skill_status


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_copy_upgrade_stale_file_is_noticed(tmp_path: Path) -> None:
    """Copy mode notices when the bundled file changed (a wheel upgrade) but the
    on-disk copy did not, and refuses to overwrite the stale copy without force."""
    src_old = _write(tmp_path / "bundle_v1.md", "SKILL v1\n")
    dest = tmp_path / "dest" / "SKILL.md"

    install_skill(dest, mode="copy", src=src_old)
    assert dest.read_text() == "SKILL v1\n"
    assert skill_status(dest, src=src_old) == "up-to-date"

    # Simulate a wheel upgrade: the bundled content changes, the on-disk copy does not.
    src_new = _write(tmp_path / "bundle_v2.md", "SKILL v2 (upgraded)\n")
    assert skill_status(dest, src=src_new) == "drifted"

    with pytest.raises(FileExistsError):
        install_skill(dest, mode="copy", src=src_new)  # stale copy, no force -> refused
    assert dest.read_text() == "SKILL v1\n"  # untouched

    install_skill(dest, mode="copy", src=src_new, force=True)
    assert dest.read_text() == "SKILL v2 (upgraded)\n"
    assert skill_status(dest, src=src_new) == "up-to-date"


def test_copy_refuses_to_clobber_user_edited_file(tmp_path: Path) -> None:
    """Copy mode refuses to overwrite a hand-edited local file without --force."""
    src = _write(tmp_path / "bundle.md", "bundled content\n")
    dest = tmp_path / "dest" / "SKILL.md"

    install_skill(dest, mode="copy", src=src)
    _write(dest, "my local edits\n")  # user edits the installed file
    assert skill_status(dest, src=src) == "drifted"

    with pytest.raises(FileExistsError):
        install_skill(dest, mode="copy", src=src)  # no force -> refused
    assert dest.read_text() == "my local edits\n"  # edits preserved

    install_skill(dest, mode="copy", src=src, force=True)
    assert dest.read_text() == "bundled content\n"


def test_copy_identical_file_is_idempotent(tmp_path: Path) -> None:
    """Re-installing an identical copy is a no-op success, not a refusal."""
    src = _write(tmp_path / "bundle.md", "same\n")
    dest = tmp_path / "dest" / "SKILL.md"
    install_skill(dest, mode="copy", src=src)
    # Second call with no force must not raise, because there is nothing to lose.
    install_skill(dest, mode="copy", src=src)
    assert dest.read_text() == "same\n"


def test_symlink_mode_links_to_bundled_path(tmp_path: Path) -> None:
    """Symlink mode makes the destination a symlink that resolves to the bundle."""
    src = _write(tmp_path / "bundle.md", "linked content\n")
    dest = tmp_path / "dest" / "SKILL.md"

    install_skill(dest, mode="symlink", src=src)
    assert dest.is_symlink()
    assert os.path.realpath(dest) == os.path.realpath(src)
    assert skill_status(dest, src=src) == "symlink-ok"
    assert dest.read_text() == "linked content\n"

    # A symlink auto-reflects a bundle change with zero drift (no re-run needed).
    src.write_text("upgraded via symlink\n")
    assert dest.read_text() == "upgraded via symlink\n"
    assert skill_status(dest, src=src) == "symlink-ok"


def test_symlink_refuses_to_replace_real_file_without_force(tmp_path: Path) -> None:
    """Symlink mode will not replace a real (possibly edited) file without force."""
    src = _write(tmp_path / "bundle.md", "bundled\n")
    dest = tmp_path / "dest" / "SKILL.md"
    install_skill(dest, mode="copy", src=src)  # dest is now a real file
    _write(dest, "local edits\n")

    with pytest.raises(FileExistsError):
        install_skill(dest, mode="symlink", src=src)
    assert not dest.is_symlink()
    assert dest.read_text() == "local edits\n"

    install_skill(dest, mode="symlink", src=src, force=True)
    assert dest.is_symlink()
    assert os.path.realpath(dest) == os.path.realpath(src)


def test_default_bundled_source_installs(tmp_path: Path) -> None:
    """With no src override, install_skill copies the real bundled SKILL.md."""
    dest = tmp_path / "dest" / "SKILL.md"
    install_skill(dest, mode="copy")
    assert dest.read_text() == bundled_skill_path().read_text()
