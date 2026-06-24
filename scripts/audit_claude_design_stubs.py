#!/usr/bin/env python3
"""Audit the repository for Claude Design stub markers and likely unmarked fake data.

Three categories, each with its own exit code so a continuous-integration
gate can fail with the right signal. See
`docs/CLAUDE_DESIGN_STUB_PROTOCOL.md` step 2.

Exit codes:
  0 -> clean.
  1 -> CLAUDE_DESIGN_WIRE_ME_UP placeholders remain inside dashboard/src/
       (build in progress, blocks final ship).
  2 -> __CLAUDE_DESIGN_STUB__ labels exist in a code path (bug, the strip
       step was skipped or bypassed).
  3 -> Heuristic indicators of unmarked fake data inside dashboard/src/.
  4 -> Internal error in the audit script itself.

Usage:

    uv run python scripts/audit_claude_design_stubs.py
    uv run python scripts/audit_claude_design_stubs.py --root /path/to/repo --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from _claude_design_stub_contract import (
    CLAUDE_DESIGN_MARKER_AUDIT_EXTENSIONS,
    CLAUDE_DESIGN_STUB_RE,
    CLAUDE_DESIGN_WIRE_RE,
    ClaudeDesignStubProtocolError,
)


class ClaudeDesignAuditCategory(StrEnum):
    """The three audit categories. Each maps to one exit code (see module docstring)."""

    WIRE_ME_UP = "claude_design_wire_me_up"  # exit 1
    UNSTRIPPED_STUB = "claude_design_unstripped_stub"  # exit 2
    HEURISTIC_FAKE = "claude_design_heuristic_fake"  # exit 3


# Directories that hold documentation, design exports, or pre-export prompts.
# These are not operator-facing surfaces, so any marker found inside is
# treated as documentation, not as a finding.
CLAUDE_DESIGN_DOC_DIRS: Final[frozenset[str]] = frozenset(
    {"_design_bundle", "design", "docs"}
)

# Code-path directories where the CLAUDE_DESIGN_WIRE_ME_UP marker is
# meaningful. A marker here means the wiring step is incomplete and the
# slice cannot ship.
CLAUDE_DESIGN_WIRE_CODE_DIRS: Final[tuple[str, ...]] = ("dashboard/src",)

# Heuristic checks run only on the live dashboard tree, because backend code
# is governed by section 4 of coding-practices.md and its numeric literals
# are real configuration, not fake data.
CLAUDE_DESIGN_HEURISTIC_SCAN_DIRS: Final[tuple[str, ...]] = ("dashboard/src",)

# Heuristic patterns that flag likely-unmarked fake data inside JSX text.
CLAUDE_DESIGN_HEURISTIC_PATTERNS: Final[
    tuple[tuple[str, re.Pattern[str]], ...]
] = (
    ("four_plus_digit_numeric", re.compile(r"(?<![\w.])\d{4,}(?![\w.])")),
    ("dollar_amount", re.compile(r"\$\s?\d+(?:\.\d+)?")),
    ("percent_literal", re.compile(r"(?<!\w)\d{1,3}(?:\.\d+)?\s*%")),
    ("iso_date", re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")),
    ("todo_marker", re.compile(r"\b(?:TODO|FIXME|XXX)\b")),
    ("lorem_ipsum", re.compile(r"\b[Ll]orem\s+ipsum\b")),
    (
        "sample_keyword",
        re.compile(r"\b(?:sample|example)\b\s*[:=]?\s*\d", re.IGNORECASE),
    ),
)

# Tests own their own fixtures and constants, so skip them in the heuristic
# phase.
CLAUDE_DESIGN_HEURISTIC_SKIP_FILE_PARTS: Final[frozenset[str]] = frozenset(
    {"tests", "__tests__", ".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts"}
)

# Root-level Markdown files that may legitimately reference the markers in
# narrative form (handoff docs, contributing notes, bug-prevention checklist).
CLAUDE_DESIGN_ROOT_DOC_SUFFIX: Final[str] = ".md"


@dataclass(frozen=True, slots=True)
class ClaudeDesignFinding:
    """One reportable line. Plain data, sortable by file then line for stable diffs."""

    category: ClaudeDesignAuditCategory
    file: Path
    line: int
    excerpt: str
    detail: str

    def to_row(self) -> dict[str, str | int]:
        return {
            "category": self.category.value,
            "file": self.file.as_posix(),
            "line": self.line,
            "excerpt": self.excerpt,
            "detail": self.detail,
        }


@dataclass(slots=True)
class ClaudeDesignAuditReport:
    """Claude Design audit findings grouped by category, ordered by file then line."""

    findings_by_category: dict[
        ClaudeDesignAuditCategory, list[ClaudeDesignFinding]
    ] = field(default_factory=dict)

    def add(self, finding: ClaudeDesignFinding) -> None:
        self.findings_by_category.setdefault(finding.category, []).append(finding)

    def exit_code(self) -> int:
        if self.findings_by_category.get(
            ClaudeDesignAuditCategory.UNSTRIPPED_STUB
        ):
            return 2
        if self.findings_by_category.get(
            ClaudeDesignAuditCategory.HEURISTIC_FAKE
        ):
            return 3
        if self.findings_by_category.get(ClaudeDesignAuditCategory.WIRE_ME_UP):
            return 1
        return 0

    def render_text(self) -> str:
        if not self.findings_by_category:
            return (
                "audit_claude_design_stubs: clean. No Claude Design stub "
                "markers and no heuristic findings."
            )
        lines: list[str] = []
        # Stable order: worst-first reading.
        order = (
            ClaudeDesignAuditCategory.UNSTRIPPED_STUB,
            ClaudeDesignAuditCategory.HEURISTIC_FAKE,
            ClaudeDesignAuditCategory.WIRE_ME_UP,
        )
        for cat in order:
            items = self.findings_by_category.get(cat, [])
            if not items:
                continue
            lines.append(f"\n[{cat.value}] {len(items)} finding(s):")
            for f in sorted(items, key=lambda x: (x.file.as_posix(), x.line)):
                lines.append(f"  {f.file.as_posix()}:{f.line}: {f.detail}")
                lines.append(f"    excerpt: {f.excerpt}")
        return "\n".join(lines)

    def render_json(self) -> str:
        payload = {
            "exit_code": self.exit_code(),
            "findings": [
                f.to_row()
                for cat in self.findings_by_category
                for f in self.findings_by_category[cat]
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=True)


def audit_claude_design(root: Path) -> ClaudeDesignAuditReport:
    """Walk `root`, return findings across all three Claude Design categories."""

    report = ClaudeDesignAuditReport()
    for path in _walk(root):
        rel = path.relative_to(root)
        text = _safe_read(path)
        if text is None:
            continue
        _check_claude_design_stub_markers(rel, text, report)
        _check_claude_design_wire_markers(rel, text, report)

    for scan_root in CLAUDE_DESIGN_HEURISTIC_SCAN_DIRS:
        scan_path = root / scan_root
        if not scan_path.exists():
            continue
        for path in _walk(scan_path):
            rel = path.relative_to(root)
            if _should_skip_heuristic(rel):
                continue
            text = _safe_read(path)
            if text is None:
                continue
            _check_claude_design_heuristics(rel, text, report)

    return report


def _walk(root: Path) -> Iterator[Path]:
    """Walk `root` yielding files whose extension is in CLAUDE_DESIGN_MARKER_AUDIT_EXTENSIONS.

    Skips dotfiles, node_modules, virtual environments, and build outputs so
    the audit stays fast and predictable.
    """

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        if any(
            skip in path.parts
            for skip in (
                "node_modules",
                ".venv",
                "dist",
                "build",
                "crucible.egg-info",
            )
        ):
            continue
        if path.suffix.lower() not in CLAUDE_DESIGN_MARKER_AUDIT_EXTENSIONS:
            continue
        yield path


def _safe_read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _is_documentation_path(rel: Path) -> bool:
    """A documentation path is any file inside CLAUDE_DESIGN_DOC_DIRS or a
    Markdown file at the repository root.

    Markers inside documentation paths are narrative, not code, so they do
    not trigger findings.
    """

    if rel.parts and rel.parts[0] in CLAUDE_DESIGN_DOC_DIRS:
        return True
    if len(rel.parts) == 1 and rel.suffix.lower() == CLAUDE_DESIGN_ROOT_DOC_SUFFIX:
        return True
    return False


def _is_wire_code_path(rel: Path) -> bool:
    posix = rel.as_posix()
    return any(
        posix.startswith(prefix + "/")
        for prefix in CLAUDE_DESIGN_WIRE_CODE_DIRS
    )


def _check_claude_design_stub_markers(
    rel: Path, text: str, report: ClaudeDesignAuditReport
) -> None:
    if _is_documentation_path(rel):
        return
    for match in CLAUDE_DESIGN_STUB_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        report.add(
            ClaudeDesignFinding(
                category=ClaudeDesignAuditCategory.UNSTRIPPED_STUB,
                file=rel,
                line=line,
                excerpt=_excerpt(text, match.start(), match.end()),
                detail=(
                    "__CLAUDE_DESIGN_STUB__ label found in a code path. Run "
                    "`uv run python scripts/strip_claude_design_stubs.py` "
                    "before copying the bundle into dashboard/src/pages/."
                ),
            )
        )


def _check_claude_design_wire_markers(
    rel: Path, text: str, report: ClaudeDesignAuditReport
) -> None:
    if not _is_wire_code_path(rel):
        return
    for match in CLAUDE_DESIGN_WIRE_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        report.add(
            ClaudeDesignFinding(
                category=ClaudeDesignAuditCategory.WIRE_ME_UP,
                file=rel,
                line=line,
                excerpt=_excerpt(text, match.start(), match.end()),
                detail=(
                    f"CLAUDE_DESIGN_WIRE_ME_UP["
                    f"{match.group('key')}|{match.group('kind')}] needs a "
                    "real hook binding. See "
                    "_design_bundle/_claude_design_stub_manifest.json."
                ),
            )
        )


def _should_skip_heuristic(rel: Path) -> bool:
    name = rel.name
    if any(skip in name for skip in CLAUDE_DESIGN_HEURISTIC_SKIP_FILE_PARTS):
        return True
    if any(part in CLAUDE_DESIGN_HEURISTIC_SKIP_FILE_PARTS for part in rel.parts):
        return True
    return False


def _check_claude_design_heuristics(
    rel: Path, text: str, report: ClaudeDesignAuditReport
) -> None:
    for name, pattern in CLAUDE_DESIGN_HEURISTIC_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            report.add(
                ClaudeDesignFinding(
                    category=ClaudeDesignAuditCategory.HEURISTIC_FAKE,
                    file=rel,
                    line=line,
                    excerpt=_excerpt(text, match.start(), match.end()),
                    detail=(
                        f"heuristic[{name}] suggests unmarked Claude Design "
                        "fake data. Wrap with "
                        "__CLAUDE_DESIGN_STUB__[key|kind|hint]__...__/"
                        "CLAUDE_DESIGN_STUB__ in the design bundle, or "
                        "replace with a real hook value."
                    ),
                )
            )


def _excerpt(text: str, start: int, end: int, *, pad: int = 40) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return text[lo:hi].replace("\n", " ").strip()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit the repo for Claude Design stub markers and likely "
            "unmarked fake data. See docs/CLAUDE_DESIGN_STUB_PROTOCOL.md."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Repository root to audit (default: current directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit findings as JSON instead of human-readable text.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        report = audit_claude_design(args.root.resolve())
    except ClaudeDesignStubProtocolError as exc:
        print(f"audit_claude_design_stubs: {exc}", file=sys.stderr)
        return 4
    if args.json:
        print(report.render_json())
    else:
        print(report.render_text())
    return report.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
