"""The cost meter. Anthropic spend is tracked per call and aggregated; the dashboard
reads the per-row ``dollars`` columns, but an in-process meter lets a run enforce its
budget ceiling (spec US-1) without a database round trip per call."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CostMeter:
    total_dollars: float = 0.0
    n_calls: int = 0

    def add(self, dollars: float) -> None:
        self.total_dollars += dollars
        self.n_calls += 1

    def remaining(self, ceiling: float) -> float:
        return max(0.0, ceiling - self.total_dollars)

    def exceeded(self, ceiling: float) -> bool:
        return self.total_dollars >= ceiling
