"""Disclosed verification scheme (PR3 port B3).

Each oracle kind ships a README.md describing how it verifies. The same text is the
oracle's ``protocol_description``: the red agent reads it in white-box mode and the
dashboard renders it on the strategy catalog, so the attacker and the operator see the
exact same disclosed scheme (single point of truth). This module loads the name (the
README's H1) and the first paragraph for each of the five oracle kinds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from shared.types.enums import OracleKind

_ORACLE_DIR = Path(__file__).resolve().parent
# Display order matches the ensemble: the four full-weight oracles, then the half-vote judge.
_ORDER = (
    OracleKind.held_out,
    OracleKind.metamorphic,
    OracleKind.differential,
    OracleKind.property_fuzz,
    OracleKind.llm_judge,
)


def _readme(kind: OracleKind) -> Path:
    return _ORACLE_DIR / str(kind) / "README.md"


def protocol_description(kind: OracleKind) -> str:
    """The first paragraph of the oracle's README: its disclosed verification scheme.

    Raises FileNotFoundError if the README is missing (loud, per coding-practices.md) so a
    new oracle without its disclosure is caught rather than silently rendering blank."""
    text = _readme(kind).read_text(encoding="utf-8")
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    for block in blocks:
        if not block.startswith("#"):
            return " ".join(block.splitlines())
    return ""


def protocol_name(kind: OracleKind) -> str:
    """The README's H1 (e.g. 'Held-out oracle'), or the kind if there is no heading."""
    text = _readme(kind).read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return str(kind)


def oracle_protocols() -> list[dict[str, Any]]:
    """Name + first-paragraph disclosure for every oracle kind, in ensemble order."""
    return [
        {"kind": str(kind), "name": protocol_name(kind), "description": protocol_description(kind)}
        for kind in _ORDER
    ]
