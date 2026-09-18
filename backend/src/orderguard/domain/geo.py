"""Minimal 2D geometry for the synthetic marketplace.

Coordinates are plain kilometers on a flat square grid, not lat/lon. A flat
grid is the right level of fidelity here: OrderGuard is predicting *failure*,
not routing, so real road networks and map projections would add complexity
with no effect on the thing being measured. MapLibre GL (Milestone 7) can
still render these by treating them as an arbitrary local projection.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot


@dataclass(frozen=True, slots=True)
class Point:
    x_km: float
    y_km: float

    def distance_to(self, other: Point) -> float:
        return hypot(self.x_km - other.x_km, self.y_km - other.y_km)
