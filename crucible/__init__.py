"""Crucible CLI front-end. Runs the full red, verify, harden, measure loop from the
terminal with no web app required. The loop, oracles, and agents are the existing
deterministic core (orchestrator/, modules/, shared/); this package adds the CLI and
the observability spine wiring on top, never a parallel implementation."""

from __future__ import annotations

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from crucible.cli import main as _main

    return _main(argv)
