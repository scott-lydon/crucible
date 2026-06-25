"""The opaque task record for the code-agent victim.

A ``CodeTask`` is what the victim is GIVEN: a function signature, a natural-
language description, a few VISIBLE example tests, and a richer SEALED held-out
test set the producer never sees. The producer writes Python source for the
function from the signature + description + VISIBLE tests only; the held-out
oracle later runs that source against the SEALED tests inside the sandbox.

The harness treats this as an opaque ``sample`` — it never inspects the type.
Only ``orchestrator/wiring.py`` (the composition root) may import this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CodeCase:
    """One test case: call ``func(*args)`` and assert it equals ``expected``.

    ``args`` is the positional argument tuple; ``expected`` is the value the
    correct implementation must return. Kept as plain data so it serializes and
    so the sandboxed runner can rebuild the assertion deterministically.
    """

    args: tuple[object, ...]
    expected: object


@dataclass(frozen=True, slots=True)
class CodeTask:
    """A code-generation task with VISIBLE and SEALED held-out tests.

    ``held_out_tests`` are oracle-only: they are NEVER placed in the producer's
    prompt (see ``producer.py``), so a reward-hacking producer that special-cases
    the visible tests still fails the held-out set. ``name`` doubles as the
    harness ``txn_index`` source via :attr:`txn_index`.
    """

    # Harness convention: every sample exposes a stable integer index.
    txn_index: int
    name: str
    signature: str  # e.g. "def is_palindrome(s: str) -> bool:"
    description: str
    visible_tests: tuple[CodeCase, ...]
    # SEALED: oracle-only. The producer never sees these.
    held_out_tests: tuple[CodeCase, ...] = field(default=())
