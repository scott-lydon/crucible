"""Single point of truth for the Claude Design stub label format.

Imported by `strip_claude_design_stubs.py` and `audit_claude_design_stubs.py`.
The label format, the regexes, and the typed errors live here and only here,
so a change to the format ripples to both consumers without drift.

Every public symbol carries the `ClaudeDesign` prefix so that a grep for
"stub" anywhere in the repo always lands next to "Claude Design", which is
the only context in which stubbing is allowed. See
`docs/CLAUDE_DESIGN_STUB_PROTOCOL.md` for the human-readable specification.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final


class ClaudeDesignStubKind(StrEnum):
    """Closed set of stub kinds the wiring step knows how to bind."""

    NUMBER = "number"
    STRING = "string"
    PERCENT = "percent"
    CURRENCY = "currency"
    COUNT = "count"
    TIMESTAMP = "timestamp"
    ARRAY = "array"
    ENUM = "enum"


# The canonical regex. Any change here must be reflected in
# docs/CLAUDE_DESIGN_STUB_PROTOCOL.md and in design/claude-design-brief.md,
# which are the documents Claude Design reads to learn the format.
CLAUDE_DESIGN_STUB_RE: Final[re.Pattern[str]] = re.compile(
    r"__CLAUDE_DESIGN_STUB__\["
    r"(?P<key>[A-Za-z0-9_.\[\]\-]+)\|"
    r"(?P<kind>number|string|percent|currency|count|timestamp|array|enum)\|"
    r"(?P<hint>[^\]]*)"
    r"\]__"
    r"(?P<value>.*?)"
    r"__/CLAUDE_DESIGN_STUB__",
    flags=re.DOTALL,
)

# The post-strip placeholder. Carries the key and the kind so the wiring step
# can find the right hook without re-reading the manifest. Prefixed with
# `CLAUDE_DESIGN_` so the post-stub state stays explicitly associated with
# the source.
CLAUDE_DESIGN_WIRE_RE: Final[re.Pattern[str]] = re.compile(
    r"CLAUDE_DESIGN_WIRE_ME_UP\["
    r"(?P<key>[A-Za-z0-9_.\[\]\-]+)\|"
    r"(?P<kind>[a-z]+)"
    r"\]"
)

# File extensions the strip script walks. HTML and JSX for the wireframes
# and pages, CSS for stubbed pseudo-content, MD and JSON for any narrative
# or manifest leakage. Backend code is not stripped, only audited.
CLAUDE_DESIGN_FILE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".css", ".md", ".json"}
)

# File extensions the audit walks when looking for `__CLAUDE_DESIGN_STUB__`
# and `CLAUDE_DESIGN_WIRE_ME_UP` markers. Broader than
# CLAUDE_DESIGN_FILE_EXTENSIONS because a stray label can hide in a backend
# module or a config file just as easily as in a frontend page. The label
# format is specific enough that a literal match in any of these is a real
# finding, never a false positive.
CLAUDE_DESIGN_MARKER_AUDIT_EXTENSIONS: Final[frozenset[str]] = (
    CLAUDE_DESIGN_FILE_EXTENSIONS
    | frozenset({".py", ".yml", ".yaml", ".toml", ".ini", ".sh", ".txt"})
)


class ClaudeDesignStubProtocolError(Exception):
    """Base class for typed errors this contract raises.

    Caught only at the script entry points so the audit and strip scripts can
    print a precise message and exit with a typed code.
    """


class UnknownClaudeDesignStubKindError(ClaudeDesignStubProtocolError):
    """A label declared a `kind` not in `ClaudeDesignStubKind`.

    The regex already enforces the closed set, so reaching this error means a
    consumer manually parsed a `kind` field instead of going through
    `ClaudeDesignStub.from_match`.
    """

    def __init__(self, raw_kind: str) -> None:
        super().__init__(
            f"Unknown Claude Design stub kind {raw_kind!r}. Allowed values: "
            f"{', '.join(k.value for k in ClaudeDesignStubKind)}. "
            "Update docs/CLAUDE_DESIGN_STUB_PROTOCOL.md if a new kind is "
            "genuinely needed."
        )
        self.raw_kind = raw_kind


@dataclass(frozen=True, slots=True)
class ClaudeDesignStub:
    """One matched Claude Design stub label, with its location for the manifest.

    Frozen and slotted per coding-practices.md section 6 ("Strict typing":
    value objects are immutable). Build instances via
    `ClaudeDesignStub.from_match`.
    """

    key: str
    kind: ClaudeDesignStubKind
    hint: str
    design_value: str
    file: Path
    line: int

    @classmethod
    def from_match(
        cls, match: re.Match[str], file: Path, line: int
    ) -> ClaudeDesignStub:
        """Build a ClaudeDesignStub from a `CLAUDE_DESIGN_STUB_RE` match.

        Raises `UnknownClaudeDesignStubKindError` only as a defensive check.
        The regex's closed set should already have rejected an unknown kind.
        """

        raw_kind = match.group("kind")
        try:
            kind = ClaudeDesignStubKind(raw_kind)
        except ValueError as exc:
            raise UnknownClaudeDesignStubKindError(raw_kind) from exc
        return cls(
            key=match.group("key"),
            kind=kind,
            hint=match.group("hint"),
            design_value=match.group("value"),
            file=file,
            line=line,
        )

    def to_claude_design_wire_me_up(self) -> str:
        """Return the canonical post-strip placeholder for this stub.

        Example: `CLAUDE_DESIGN_WIRE_ME_UP[metric.asr|percent]`.
        """

        return f"CLAUDE_DESIGN_WIRE_ME_UP[{self.key}|{self.kind.value}]"

    def to_manifest_row(self) -> dict[str, str | int]:
        """Return a JSON-serializable dict for `_claude_design_stub_manifest.json`.

        Path is stored as a POSIX string so the manifest is platform-stable.
        """

        return {
            "key": self.key,
            "kind": self.kind.value,
            "hint": self.hint,
            "design_value": self.design_value,
            "file": self.file.as_posix(),
            "line": self.line,
        }


def iter_claude_design_files(root: Path) -> Iterator[Path]:
    """Yield every file under `root` with an extension in CLAUDE_DESIGN_FILE_EXTENSIONS.

    Skips dotfiles and `node_modules`, so a bundle that ships with a stale
    dependency directory does not poison the manifest.
    """

    if not root.exists():
        raise FileNotFoundError(
            f"Claude Design bundle directory does not exist: {root}. "
            "Pass an existing path with --bundle-dir, or run the Claude Design "
            "export per design/claude-design-brief.md first."
        )
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in CLAUDE_DESIGN_FILE_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        if "node_modules" in path.parts:
            continue
        yield path


def find_claude_design_stubs_in_text(
    text: str, file: Path
) -> Iterator[ClaudeDesignStub]:
    """Yield every ClaudeDesignStub in `text`, tagged with `file` and the 1-indexed line."""

    for match in CLAUDE_DESIGN_STUB_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        yield ClaudeDesignStub.from_match(match, file=file, line=line)
