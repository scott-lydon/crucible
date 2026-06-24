#!/usr/bin/env python3
"""Strip every `__CLAUDE_DESIGN_STUB__[...]__/CLAUDE_DESIGN_STUB__` label.

Replaces the label with `CLAUDE_DESIGN_WIRE_ME_UP[<key>|<kind>]` in place,
and writes a manifest at `<bundle>/_claude_design_stub_manifest.json`
enumerating every stub for the wiring step. Idempotent: running twice yields
an empty diff and the same manifest.

Usage:

    uv run python scripts/strip_claude_design_stubs.py --bundle-dir _design_bundle/

See `docs/CLAUDE_DESIGN_STUB_PROTOCOL.md` step 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from _claude_design_stub_contract import (
    CLAUDE_DESIGN_STUB_RE,
    ClaudeDesignStub,
    ClaudeDesignStubProtocolError,
    find_claude_design_stubs_in_text,
    iter_claude_design_files,
)


class ClaudeDesignStripError(ClaudeDesignStubProtocolError):
    """Raised when the strip step cannot complete cleanly.

    The error message names the file, the operation, and the likely fix per
    coding-practices.md section 6 ("Errors must be loud, typed, and
    self-explaining").
    """


@dataclass(frozen=True, slots=True)
class ClaudeDesignStripResult:
    """Summary of one strip run.

    Carries enough information for the caller to print a diff and decide
    whether to commit.
    """

    files_scanned: int
    files_modified: int
    stubs_replaced: int
    manifest_path: Path

    def render(self) -> str:
        return (
            f"strip_claude_design_stubs: scanned {self.files_scanned} files, "
            f"modified {self.files_modified}, replaced {self.stubs_replaced} "
            f"Claude Design stubs, manifest at {self.manifest_path.as_posix()}."
        )


def strip_claude_design_bundle(bundle_dir: Path) -> ClaudeDesignStripResult:
    """Strip every Claude Design stub in `bundle_dir` and write the manifest.

    Walks the bundle, collects every stub, substitutes
    `CLAUDE_DESIGN_WIRE_ME_UP[...]` placeholders in place, and writes the
    manifest as the last action so a crash mid-walk does not leave behind a
    half-written manifest.
    """

    all_stubs: list[ClaudeDesignStub] = []
    files_scanned = 0
    files_modified = 0

    for path in iter_claude_design_files(bundle_dir):
        files_scanned += 1
        text = _read_text(path)
        stubs = list(
            find_claude_design_stubs_in_text(
                text, file=path.relative_to(bundle_dir)
            )
        )
        if not stubs:
            continue
        all_stubs.extend(stubs)
        new_text = CLAUDE_DESIGN_STUB_RE.sub(_replacement, text)
        if new_text == text:
            raise ClaudeDesignStripError(
                f"Found {len(stubs)} Claude Design stub labels in "
                f"{path.as_posix()} but the regex substitution produced no "
                "change. The regex in scripts/_claude_design_stub_contract.py "
                "is likely out of sync with the files that ship in the bundle."
            )
        _write_text(path, new_text)
        files_modified += 1

    manifest_path = bundle_dir / "_claude_design_stub_manifest.json"
    _write_manifest(manifest_path, all_stubs, bundle_dir=bundle_dir)
    return ClaudeDesignStripResult(
        files_scanned=files_scanned,
        files_modified=files_modified,
        stubs_replaced=len(all_stubs),
        manifest_path=manifest_path,
    )


def _replacement(match: re.Match[str]) -> str:
    """Return the `CLAUDE_DESIGN_WIRE_ME_UP[...]` literal for one matched stub.

    Rebuilds a ClaudeDesignStub so the placeholder generation goes through
    the canonical `ClaudeDesignStub.to_claude_design_wire_me_up` path (single
    point of truth).
    """

    stub = ClaudeDesignStub.from_match(match, file=Path("<unknown>"), line=0)
    return stub.to_claude_design_wire_me_up()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ClaudeDesignStripError(
            f"Could not read {path.as_posix()} as UTF-8: {exc}. "
            "The Claude Design export should emit UTF-8 only. Convert the "
            "file or remove it from the bundle."
        ) from exc


def _write_text(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise ClaudeDesignStripError(
            f"Could not write {path.as_posix()}: {exc}. "
            "Check that the bundle directory is writable and not on a "
            "read-only mount."
        ) from exc


def _write_manifest(
    manifest_path: Path,
    stubs: list[ClaudeDesignStub],
    *,
    bundle_dir: Path,
) -> None:
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "bundle_dir": bundle_dir.as_posix(),
        "format_version": 1,
        "stub_count": len(stubs),
        "stubs": [stub.to_manifest_row() for stub in stubs],
    }
    try:
        manifest_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ClaudeDesignStripError(
            f"Could not write manifest to {manifest_path.as_posix()}: {exc}. "
            "The bundle directory must be writable."
        ) from exc


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Strip Claude Design stub labels and emit the wiring manifest. "
            "See docs/CLAUDE_DESIGN_STUB_PROTOCOL.md."
        )
    )
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=Path("_design_bundle"),
        help="Directory holding the Claude Design export (default: _design_bundle/).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        result = strip_claude_design_bundle(args.bundle_dir.resolve())
    except ClaudeDesignStubProtocolError as exc:
        print(f"strip_claude_design_stubs: {exc}", file=sys.stderr)
        return 1
    print(result.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
