"""Typed blue-pillar errors (PR3 port C2).

Loud and specific per coding-practices.md section 6: a contaminated held-out set is a
correctness failure, not a recovery to report, so it raises rather than returning a number.
"""

from __future__ import annotations

from shared.types.errors import CrucibleError


class HoldoutContamination(CrucibleError):  # noqa: N818 — name fixed by PR #3 / checklist C2
    """The held-out validation set overlaps the attacks the patch was trained on.

    A held-out score that shares examples with training is leakage, not validation, so the
    validator refuses it. The message names how many ids overlap and the first few of them.
    """
