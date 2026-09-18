"""Driver entity.

`idle_minutes` is tracked explicitly (rather than derived from timestamps at
query time) because it's mutated every tick by the simulation engine and is a
first-class, directly observable risk factor: a driver idle for a long
stretch before assignment is more likely to be distracted, off-app, or about
to go offline than one that just finished a delivery.
"""

from __future__ import annotations

from dataclasses import dataclass

from orderguard.domain.enums import DriverStatus
from orderguard.domain.geo import Point


@dataclass(slots=True)
class Driver:
    id: str
    name: str
    location: Point
    speed_kmh: float
    reliability_score: float
    """Probability-scaling factor in [0, 1]; lower means more prone to going
    offline mid-delivery or taking implausible detours."""

    status: DriverStatus = DriverStatus.AVAILABLE
    current_delivery_id: str | None = None
    idle_minutes: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.reliability_score <= 1.0:
            raise ValueError(f"reliability_score must be in [0, 1], got {self.reliability_score}")
        if self.speed_kmh <= 0:
            raise ValueError(f"speed_kmh must be > 0, got {self.speed_kmh}")

    @property
    def is_available(self) -> bool:
        return self.status == DriverStatus.AVAILABLE

    def move_toward(self, target: Point, *, minutes: float, speed_multiplier: float) -> bool:
        """Advance `location` toward `target` by however far `speed_kmh *
        speed_multiplier` covers in `minutes`. Returns True once the driver
        has arrived (snapped exactly onto `target`, no overshoot).
        """
        remaining = self.location.distance_to(target)
        if remaining <= 1e-9:
            self.location = target
            return True

        effective_speed_kmh = self.speed_kmh * speed_multiplier
        max_travel_km = effective_speed_kmh * (minutes / 60.0)
        if max_travel_km >= remaining:
            self.location = target
            return True

        fraction = max_travel_km / remaining
        self.location = Point(
            x_km=self.location.x_km + (target.x_km - self.location.x_km) * fraction,
            y_km=self.location.y_km + (target.y_km - self.location.y_km) * fraction,
        )
        return False
