"""ProbeResult value object.

The outcome of one subcomponent self-test, surfaced on the /health page
(US-8). `detail` carries the evidence (model checksum, last training time,
the egress allow-list) so a red or amber status is diagnosable in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .enums import ProbeStatus


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """One subcomponent's self-test status and the evidence behind it."""

    status: ProbeStatus
    detail: dict[str, Any]
