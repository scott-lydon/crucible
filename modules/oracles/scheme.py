"""Verification-scheme assembler (US-14, slice-12).

The Targets-and-Oracles pillar owns describing the verification scheme — the set
of oracle protocols the platform runs against the detector. ``verification_scheme``
concatenates each oracle's ``describe()`` into one generic protocol description
that the WHITE-BOX red agent gets in its prompt, so it can craft an evasion that
fools the detector AND these verifiers.

Generic by construction: it carries NO target/domain strings of its own — it only
forwards what each oracle reports about its own MECHANISM. In particular the
held-out oracle deliberately describes only the held-out generator mechanism, not
the literal ground-truth rule (a white-box attacker that learned the exact rule
could only flip the true label, which is not a valid evasion).
"""

from collections.abc import Sequence

from orchestrator.interfaces import Oracle


def verification_scheme(oracles: Sequence[Oracle]) -> str:
    """Assemble the oracles' protocol descriptions into one numbered list.

    Each oracle contributes one line via its ``describe()``. The result is plain
    text suitable to inject into the white-box red prompt.
    """
    lines = [f"{i + 1}. {o.describe().strip()}" for i, o in enumerate(oracles)]
    return "\n".join(lines) if lines else "(no verifiers declared)"
