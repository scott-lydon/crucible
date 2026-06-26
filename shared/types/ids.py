"""Typed identifiers. NewType keeps a RunId from being passed where an AttackId is
expected, without runtime overhead. ``new_id`` is the only place identifiers are
minted, so the prefix convention stays in one spot."""

from __future__ import annotations

import uuid
from typing import NewType

RunId = NewType("RunId", str)
AttackId = NewType("AttackId", str)
VerdictId = NewType("VerdictId", str)
PatchId = NewType("PatchId", str)
LLMCallId = NewType("LLMCallId", str)
SandboxJobId = NewType("SandboxJobId", str)


def new_id(prefix: str) -> str:
    """Mint a fresh opaque identifier, e.g. ``run_3f9c1a2b4d5e``.

    Uses uuid4; never call this from a deterministic replay path — replay reads
    the persisted identifier rather than minting a new one.
    """
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
