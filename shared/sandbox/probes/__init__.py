"""Sandbox probes. The seal probe (US-9) verifies the producer is sealed."""

from __future__ import annotations

from pathlib import Path

# Absolute path to the seal-probe script, fed into the sandbox by the seal test.
SEAL_PROBE_PATH = Path(__file__).resolve().parent / "seal_probe.py"

__all__ = ["SEAL_PROBE_PATH"]
