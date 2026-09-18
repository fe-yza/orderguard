"""Customer entity."""

from __future__ import annotations

from dataclasses import dataclass

from orderguard.domain.geo import Point


@dataclass(slots=True)
class Customer:
    id: str
    name: str
    location: Point
    reachability_score: float
    """Probability-scaling factor in [0, 1]; lower means more likely to be
    unreachable at the door (contributing to `FailureReason.CUSTOMER_UNREACHABLE`)."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.reachability_score <= 1.0:
            raise ValueError(f"reachability_score must be in [0, 1], got {self.reachability_score}")
