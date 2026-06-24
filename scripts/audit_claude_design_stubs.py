#!/usr/bin/env python3
"""Audit the repository for Claude Design stub markers and likely unmarked fake data.

Three categories, each with its own exit code so a continuous-integration
gate can fail with the right signal. See
`docs/CLAUDE_DESIGN_STUB_PROTOCOL.md` step 2.

Exit codes:
  0 -> clean.
  1 -> CLAUDE_DESIGN_WIRE_ME_UP placeholders remain inside the dashboard
       tree (build in progress, blocks final ship).
  2 -> __CLAUDE_DESIGN_STUB__ labels exist in a code path (bug, the strip
       step was skipped or bypassed).
  3 -> Heuristic indicators of unmarked fake data inside a dashboard HTML
       file: a text node sits inside an element with no live-wire ancestor.
  4 -> Internal error in the audit script itself.

Usage:

    uv run python scripts/audit_claude_design_stubs.py
    uv run python scripts/audit_claude_design_stubs.py --root /path/to/repo --json
    uv run python scripts/audit_claude_design_stubs.py --strict  # fail on any finding

The script is deterministic: every finding ships with file, line, the
literal that fired the heuristic, and the canonical suggestion. Two
wire-up markers are recognized as equivalent (both keep an element out of
the heuristic):

* `__CLAUDE_DESIGN_STUB__[k|kind|hint]__value__/CLAUDE_DESIGN_STUB__`
  the wrapper this script's sibling strip step understands; and
* `data-live="<key>"`, `data-live-list="<key>"`, `data-live-row="<key>"`
  the attribute convention `frontend/live.js` already uses on the
  existing Claude Design pages.

If neither marker covers a literal-looking text node inside a dashboard
HTML file, the audit fires category 3 (heuristic) for the operator to
wire or remove.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
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


# Documentation directories. Markers found here are narrative, not code.
CLAUDE_DESIGN_DOC_DIRS: Final[frozenset[str]] = frozenset(
    {"_design_bundle", "design", "docs"}
)

# Code-path directories where CLAUDE_DESIGN_WIRE_ME_UP is meaningful.
CLAUDE_DESIGN_WIRE_CODE_DIRS: Final[tuple[str, ...]] = (
    "dashboard/src",
    "frontend",
)

# HTML files in these directories get the deep HTML-text-node heuristic.
CLAUDE_DESIGN_HTML_HEURISTIC_DIRS: Final[tuple[str, ...]] = (
    "dashboard/src",
    "frontend",
)

# Plain text-content heuristics for JSX/TSX in the dashboard tree.
CLAUDE_DESIGN_JSX_HEURISTIC_DIRS: Final[tuple[str, ...]] = ("dashboard/src",)

# Heuristic patterns applied to HTML text-node content. Each is intentionally
# narrow so it does not fire on real config (Tailwind class numbers, viewBox
# coordinates) but does catch hand-typed sample values from a Claude Design
# export.
CLAUDE_DESIGN_HTML_TEXT_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("currency_amount", re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?")),
    ("percent_literal", re.compile(r"(?<!\w)\d{1,3}(?:\.\d+)?\s*%")),
    ("multi_digit_number", re.compile(r"(?<![\w.])\d{2,}(?:\.\d+)?(?![\w.])")),
    ("iso_date", re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")),
    ("clock_time", re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")),
    ("email_literal", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    (
        "uuid_literal",
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
    ),
    ("sha_truncation", re.compile(r"\bsha\s+[0-9a-f]{4,}", re.IGNORECASE)),
    (
        "sample_name",
        re.compile(
            r"\b(?:John\s+Doe|Jane\s+Doe|Jane\s+Smith|Acme\s+(?:Corp|Inc)"
            r"|Foo\s+Bar|Lorem)\b"
        ),
    ),
    ("todo_marker", re.compile(r"\b(?:TODO|FIXME|XXX)\b")),
)

# Pure-text heuristics for JSX/TSX files (no HTML parser, regex on file text).
CLAUDE_DESIGN_JSX_TEXT_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "jsx_currency_in_text",
        re.compile(r">[^<{}]*?\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?[^<{}]*?<"),
    ),
    (
        "jsx_percent_in_text",
        re.compile(r">[^<{}]*?(?<!\w)\d{1,3}(?:\.\d+)?\s*%[^<{}]*?<"),
    ),
    (
        "jsx_iso_date_in_text",
        re.compile(r">[^<{}]*?\b20\d{2}-\d{2}-\d{2}\b[^<{}]*?<"),
    ),
)

# Tests own their own fixtures and constants.
CLAUDE_DESIGN_HEURISTIC_SKIP_FILE_PARTS: Final[frozenset[str]] = frozenset(
    {"tests", "__tests__", ".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts"}
)

# Tags that contain non-user content. Their text bodies are skipped.
CLAUDE_DESIGN_HTML_NON_CONTENT_TAGS: Final[frozenset[str]] = frozenset(
    {"script", "style", "noscript", "template"}
)

# Tag attributes that mark a node (and its descendants) as wired.
CLAUDE_DESIGN_WIRE_ATTRIBUTES: Final[frozenset[str]] = frozenset(
    {"data-live", "data-live-list", "data-live-row"}
)

# Markdown extension for root-level docs.
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

    def total_findings(self) -> int:
        return sum(len(v) for v in self.findings_by_category.values())

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
        order = (
            ClaudeDesignAuditCategory.UNSTRIPPED_STUB,
            ClaudeDesignAuditCategory.HEURISTIC_FAKE,
            ClaudeDesignAuditCategory.WIRE_ME_UP,
        )
        total = self.total_findings()
        lines.append(f"audit_claude_design_stubs: {total} total finding(s).")
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

    def render_summary_by_file(self) -> str:
        """Per-file count summary for category 3, useful for slice-by-slice triage."""

        by_file: dict[str, int] = {}
        for cat in (
            ClaudeDesignAuditCategory.HEURISTIC_FAKE,
            ClaudeDesignAuditCategory.WIRE_ME_UP,
        ):
            for f in self.findings_by_category.get(cat, []):
                by_file[f.file.as_posix()] = by_file.get(f.file.as_posix(), 0) + 1
        if not by_file:
            return "no heuristic findings per file."
        lines = ["heuristic / wire findings by file (count, path):"]
        for path, count in sorted(by_file.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {count:4d}  {path}")
        return "\n".join(lines)


class _LiveAncestryHtmlParser(HTMLParser):
    """Stream-parse HTML, emitting (text, line, has_live_ancestor) for each text node.

    `has_live_ancestor` is True if any open element in the stack carries one
    of the wire attributes in CLAUDE_DESIGN_WIRE_ATTRIBUTES, or if the
    captured text already contains a CLAUDE_DESIGN_STUB / WIRE_ME_UP marker
    (which the operator has tagged explicitly).
    """

    def __init__(self) -> None:
        # convert_charrefs=False so we get literal text positions back; we
        # are not building a DOM, only proximity facts.
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool]] = []  # (tag, contributes_live)
        self._non_content_depth = 0
        self.text_nodes: list[tuple[str, int, bool]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        live = any(a in CLAUDE_DESIGN_WIRE_ATTRIBUTES for a, _ in attrs)
        self._stack.append((tag, live))
        if tag in CLAUDE_DESIGN_HTML_NON_CONTENT_TAGS:
            self._non_content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        # Pop matching tag; if mismatched (common in real-world HTML),
        # pop until we find it or stack is empty.
        while self._stack:
            popped_tag, _ = self._stack.pop()
            if popped_tag == tag:
                break
        if tag in CLAUDE_DESIGN_HTML_NON_CONTENT_TAGS and self._non_content_depth > 0:
            self._non_content_depth -= 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        # Self-closing tags do not nest; we don't add them to the stack.
        pass

    def handle_data(self, data: str) -> None:
        if self._non_content_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        line, _col = self.getpos()
        has_live_ancestor = any(live for _tag, live in self._stack)
        # Self-tag check: text containing a Claude Design marker also
        # counts as "covered".
        if CLAUDE_DESIGN_STUB_RE.search(text) or CLAUDE_DESIGN_WIRE_RE.search(text):
            has_live_ancestor = True
        self.text_nodes.append((text, line, has_live_ancestor))


def audit_claude_design(root: Path) -> ClaudeDesignAuditReport:
    """Walk `root`, return findings across all three Claude Design categories."""

    report = ClaudeDesignAuditReport()

    # Stub and wire marker pass: every code-path-eligible file.
    for path in _walk(root):
        rel = path.relative_to(root)
        text = _safe_read(path)
        if text is None:
            continue
        _check_claude_design_stub_markers(rel, text, report)
        _check_claude_design_wire_markers(rel, text, report)

    # HTML heuristic pass: dashboard-tree HTML files.
    for scan_root in CLAUDE_DESIGN_HTML_HEURISTIC_DIRS:
        scan_path = root / scan_root
        if not scan_path.exists():
            continue
        for path in _walk(scan_path):
            if path.suffix.lower() not in {".html", ".htm"}:
                continue
            rel = path.relative_to(root)
            if _should_skip_heuristic(rel):
                continue
            text = _safe_read(path)
            if text is None:
                continue
            _check_html_text_heuristics(rel, text, report)

    # JSX heuristic pass: dashboard-tree JSX/TSX files.
    for scan_root in CLAUDE_DESIGN_JSX_HEURISTIC_DIRS:
        scan_path = root / scan_root
        if not scan_path.exists():
            continue
        for path in _walk(scan_path):
            if path.suffix.lower() not in {".jsx", ".tsx"}:
                continue
            rel = path.relative_to(root)
            if _should_skip_heuristic(rel):
                continue
            text = _safe_read(path)
            if text is None:
                continue
            _check_jsx_text_heuristics(rel, text, report)

    return report


def _walk(root: Path) -> Iterator[Path]:
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
    if rel.parts and rel.parts[0] in CLAUDE_DESIGN_DOC_DIRS:
        return True
    if len(rel.parts) == 1 and rel.suffix.lower() == CLAUDE_DESIGN_ROOT_DOC_SUFFIX:
        return True
    return False


def _is_wire_code_path(rel: Path) -> bool:
    posix = rel.as_posix()
    return any(
        posix == prefix or posix.startswith(prefix + "/")
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


def _check_html_text_heuristics(
    rel: Path, text: str, report: ClaudeDesignAuditReport
) -> None:
    parser = _LiveAncestryHtmlParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        # HTML parsing is best-effort; one weird file should not abort the
        # whole audit.
        report.add(
            ClaudeDesignFinding(
                category=ClaudeDesignAuditCategory.HEURISTIC_FAKE,
                file=rel,
                line=1,
                excerpt=str(exc)[:80],
                detail=(
                    "HTML parser bailed on this file. Inspect manually for "
                    "stubbed values; the audit could not deterministically "
                    "scope by live ancestor."
                ),
            )
        )
        return

    for content, line, has_live_ancestor in parser.text_nodes:
        if has_live_ancestor:
            continue
        for pattern_name, pattern in CLAUDE_DESIGN_HTML_TEXT_PATTERNS:
            for match in pattern.finditer(content):
                report.add(
                    ClaudeDesignFinding(
                        category=ClaudeDesignAuditCategory.HEURISTIC_FAKE,
                        file=rel,
                        line=line,
                        excerpt=_excerpt(content, match.start(), match.end()),
                        detail=(
                            f"heuristic[html:{pattern_name}] suggests unmarked "
                            "Claude Design fake data in a text node with no "
                            "data-live ancestor. Tag the node with "
                            "data-live=\"<key>\" and wire in frontend/live.js, "
                            "or wrap with __CLAUDE_DESIGN_STUB__[k|kind|h]__"
                            "...__/CLAUDE_DESIGN_STUB__ if the design bundle "
                            "is still authoring."
                        ),
                    )
                )


def _check_jsx_text_heuristics(
    rel: Path, text: str, report: ClaudeDesignAuditReport
) -> None:
    for pattern_name, pattern in CLAUDE_DESIGN_JSX_TEXT_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            report.add(
                ClaudeDesignFinding(
                    category=ClaudeDesignAuditCategory.HEURISTIC_FAKE,
                    file=rel,
                    line=line,
                    excerpt=_excerpt(text, match.start(), match.end()),
                    detail=(
                        f"heuristic[jsx:{pattern_name}] suggests unmarked "
                        "Claude Design fake data. Wrap with "
                        "__CLAUDE_DESIGN_STUB__[key|kind|hint]__...__/"
                        "CLAUDE_DESIGN_STUB__ in the design bundle, or "
                        "replace with a real hook value."
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
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print only the per-file count summary (handy for triage).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Exit non-zero on any finding, including category 1 "
            "(WIRE_ME_UP placeholders). Default fails only on category 2 "
            "(unstripped stubs) or 3 (heuristic)."
        ),
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
    elif args.summary:
        print(report.render_summary_by_file())
    else:
        print(report.render_text())
    code = report.exit_code()
    # Default behavior already returns the right code; --strict only matters
    # when the only findings are WIRE_ME_UP (category 1). The contract docs
    # call exit 1 "blocks final ship", so strict mode promotes it.
    if args.strict and code == 1:
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
