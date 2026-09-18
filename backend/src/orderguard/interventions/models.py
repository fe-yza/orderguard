"""Intervention engine output types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, auto


class InterventionType(StrEnum):
    DO_NOTHING = auto()
    UPDATE_ETA = auto()
    NOTIFY_CUSTOMER = auto()
    NOTIFY_MERCHANT = auto()
    MERCHANT_ESCALATION = auto()
    OFFER_CREDIT = auto()
    REASSIGN_DRIVER = auto()


@dataclass(frozen=True, slots=True)
class InterventionCandidate:
    """One intervention's expected-value math, whether or not it was chosen.
    Kept around (not just the winner) so the Order Inspector UI (Milestone 7)
    can show the full cost comparison, not just the decision."""

    intervention_type: InterventionType
    direct_cost: float
    failure_probability: float
    """Risk-assessment score treated as an implied failure probability — a
    modeling simplification (see `interventions/engine.py`), not a
    calibrated probability."""
    failure_cost: float
    probability_reduction: float
    """Fractional reduction in failure probability this intervention buys
    (0 for interventions that only soften impact rather than prevent it)."""
    cost_reduction_fraction: float
    """Fractional reduction in failure *cost/impact* this intervention buys
    (0 for interventions that address the root cause instead)."""
    residual_expected_failure_cost: float
    total_expected_cost: float
    """direct_cost + residual_expected_failure_cost — what the expected-value
    model actually minimizes over."""


@dataclass(slots=True)
class InterventionDecision:
    id: str
    order_id: str
    delivery_id: str | None
    risk_assessment_id: str
    computed_at: datetime
    chosen: InterventionType
    rationale: str
    candidates: list[InterventionCandidate] = field(default_factory=list)
    """All applicable candidates, sorted ascending by `total_expected_cost`
    — `candidates[0]` is `chosen`."""

    @property
    def chosen_candidate(self) -> InterventionCandidate:
        return next(c for c in self.candidates if c.intervention_type == self.chosen)

    @property
    def expected_savings_vs_do_nothing(self) -> float:
        do_nothing = next(
            c for c in self.candidates if c.intervention_type == InterventionType.DO_NOTHING
        )
        return do_nothing.total_expected_cost - self.chosen_candidate.total_expected_cost
