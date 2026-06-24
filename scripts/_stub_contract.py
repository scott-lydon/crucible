"""Single point of truth for the stub label format.

Imported by `strip_design_stubs.py` and `audit_stubs.py`. The label format and
the regexes live here and only here, so a change to the format ripples to both
consumers without drift.

See `docs/STUB_PROTOCOL.md` for the human-readable specification.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final


class StubKind(StrEnum):
    """Closed set of stub kinds the wiring step knows how to bind."""

    NUMBER = "number"
    STRING = "string"
    PERCENT = "percent"
    CURRENCY = "currency"
    COUNT = "count"
    TIMESTAMP = "timestamp"
    ARRAY = "array"
    ENUM = "enum"


# The canonical regex. Any change here must be reflected in STUB_PROTOCOL.md
# and in design/claude-design-brief.md, which are the documents Claude Design
# reads to learn the format.
STUB_RE: Final[re.Pattern[str]] = re.compile(
    r"__STUB__\["
    r"(?P<key>[A-Za-z0-9_.\[\]\-]+)\|"
    r"(?P<kind>number|string|percent|currency|count|timestamp|array|enum)\|"
    r"(?P<hint>[^\]]*)"
    r"\]__"
    r"(?P<value>.*?)"
    r"__/STUB__",
    flags=re.DOTALL,
)

# The post-strip placeholder. Carries the key and the kind so the wiring step
# can find the right hook without re-reading the manifest.
WIRE_RE: Final[re.Pattern[str]] = re.compile(
    r"WIRE_ME_UP\["
    r"(?P<key>[A-Za-z0-9_.\[\]\-]+)\|"
    r"(?P<kind>[a-z]+)"
    r"\]"
)

# File extensions the strip script walks. HTML and JSX for the wireframes
# and pages, CSS for stubbed pseudo-content, MD and JSON for any narrative or
# manifest leakage. Backend code is not stripped, only audited (see below).
DESIGN_FILE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".css", ".md", ".json"}
)

# File extensions the audit walks when looking for `__STUB__` and
# `WIRE_ME_UP` markers. Broader than DESIGN_FILE_EXTENSIONS because a stray
# label can hide in a backend module or a config file just as easily as in
# a frontend page. The label format is specific enough that a literal match
# in any of these is a real finding, never a false positive.
MARKER_AUDIT_EXTENSIONS: Final[frozenset[str]] = (
    DESIGN_FILE_EXTENSIONS
    | frozenset({".py", ".yml", ".yaml", ".toml", ".ini", ".sh", ".txt"})
)


class StubProtocolError(Exception):
    """Base class for typed errors this contract raises.

    Caught only at the script entry points so the audit and strip scripts can
    print a precise message and exit with a typed code.
    """


class UnknownStubKindError(StubProtocolError):
    """A label declared a `kind` not in `StubKind`.

    The regex already enforces the closed set, so reaching this error means a
    consumer manually parsed a `kind` field instead of going through `Stub.parse`.
    """

    def __init__(self, raw_kind: str) -> None:
        super().__init__(
            f"Unknown stub kind {raw_kind!r}. Allowed values: "
            f"{', '.join(k.value for k in StubKind)}. "
            "Update docs/STUB_PROTOCOL.md if a new kind is genuinely needed."
        )
        self.raw_kind = raw_kind


@dataclass(frozen=True, slots=True)
class Stub:
    """One matched stub label, with its location for the manifest.

    Frozen and slotted per `coding-practices.md` section 6 ("Strict typing":
    value objects are immutable). The constructor is private in spirit: build
    instances via `Stub.from_match`.
    """

    key: str
    kind: StubKind
    hint: str
    design_value: str
    file: Path
    line: int

    @classmethod
    def from_match(cls, match: re.Match[str], file: Path, line: int) -> Stub:
        """Build a Stub from a `STUB_RE` match.

        Raises `UnknownStubKindError` only as a defensive check. The regex's
        closed set should already have rejected an unknown kind.
        """

        raw_kind = match.group("kind")
        try:
            kind = StubKind(raw_kind)
        except ValueError as exc:
            raise UnknownStubKindError(raw_kind) from exc
        return cls(
            key=match.group("key"),
            kind=kind,
            hint=match.group("hint"),
            design_value=match.group("value"),
            file=file,
            line=line,
        )

    def to_wire_me_up(self) -> str:
        """Return the canonical post-strip placeholder for this stub.

        Example: `WIRE_ME_UP[metric.asr|percent]`.
        """

        return f"WIRE_ME_UP[{self.key}|{self.kind.value}]"

    def to_manifest_row(self) -> dict[str, str | int]:
        """Return a JSON-serializable dict for `_stub_manifest.json`.

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


def iter_design_files(root: Path) -> Iterator[Path]:
    """Yield every file under `root` whose extension is in `DESIGN_FILE_EXTENSIONS`.

    Skips dotfiles and `node_modules`, so a bundle that ships with a stale
    dependency directory does not poison the manifest.
    """

    if not root.exists():
        raise FileNotFoundError(
            f"Design bundle directory does not exist: {root}. "
            "Pass an existing path with --bundle-dir, or run the Claude Design "
            "export per design/claude-design-brief.md first."
        )
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in DESIGN_FILE_EXTENSIONS:
            continue
        if any(part.startswith(".") for part in path.parts):
            continue
        if "node_modules" in path.parts:
            continue
        yield path


def find_stubs_in_text(text: str, file: Path) -> Iterator[Stub]:
    """Yield every Stub in `text`, tagged with `file` and the 1-indexed line."""

    for match in STUB_RE.finditer(text):
        # str.count is O(n) but the file is already in memory, so the cost is
        # bounded by the file size times the number of stubs per file.
        line = text.count("\n", 0, match.start()) + 1
        yield Stub.from_match(match, file=file, line=line)
