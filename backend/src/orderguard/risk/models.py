"""Risk engine output types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum, auto


class PredictedFailureType(StrEnum):
    """What the risk engine thinks will go wrong, if anything. Mirrors the
    simulation's `FailureReason`/`CancellationReason` causes plus
    `LATE_DELIVERY` — a delivery that will complete but miss its promise is a
    real, distinct, predictable outcome the intervention engine cares about,
    even though it isn't a domain `OrderStatus` (see `domain/order.py`)."""

    LATE_DELIVERY = auto()
    NEVER_PICKED_UP = auto()
    DRIVER_NEVER_ARRIVED = auto()
    DAMAGED_OR_SPOILED = auto()
    CUSTOMER_UNREACHABLE = auto()
    NO_DRIVER_AVAILABLE = auto()


@dataclass(frozen=True, slots=True)
class RiskFactor:
    """One rule's contribution to the overall score. `weight` is the maximum
    points this rule can contribute; `raw_signal` (always in [0, 1]) is how
    strongly the rule fired; `contribution = weight * raw_signal`."""

    name: str
    description: str
    weight: float
    raw_signal: float
    contribution: float


@dataclass(slots=True)
class RiskAssessment:
    id: str
    order_id: str
    delivery_id: str | None
    computed_at: datetime
    overall_risk_score: float
    """0-100. Normalized by the total weight of factors that were actually
    applicable at this stage of the delivery — see `risk/engine.py`."""
    predicted_failure_type: PredictedFailureType | None
    confidence: float
    """0-1 heuristic reflecting how much observable signal fed the
    assessment, not a statistically calibrated probability."""
    predicted_delay_minutes: float
    """Estimated (completion time - promised time). Negative means the
    engine expects the delivery to complete ahead of its promise."""
    factors: list[RiskFactor] = field(default_factory=list)
