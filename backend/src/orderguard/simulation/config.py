"""Simulation configuration.

Plain dataclass with validation in `__post_init__`, not Pydantic — this is
the boundary decision documented in `docs/architecture.md`: config objects
constructed by trusted internal code (generators, tests) don't need
Pydantic's validation overhead. When the Simulation Lab API (Milestone 6/7)
accepts a config from an HTTP request body, that layer will have its own
Pydantic schema that validates untrusted input and then constructs one of
these — this class is not what parses the wire format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RushHourWindow:
    """A time-of-day window, expressed as minutes elapsed since
    `SimulationConfig.start_time`, during which demand rises and travel
    slows. `demand_multiplier` scales the order arrival rate;
    `speed_multiplier` (<=1) scales driver travel speed to model congestion.
    """

    start_minute: int
    end_minute: int
    demand_multiplier: float
    speed_multiplier: float

    def __post_init__(self) -> None:
        if self.start_minute < 0 or self.end_minute <= self.start_minute:
            raise ValueError(f"invalid window [{self.start_minute}, {self.end_minute})")
        if self.demand_multiplier <= 0:
            raise ValueError("demand_multiplier must be > 0")
        if not 0 < self.speed_multiplier <= 1:
            raise ValueError("speed_multiplier must be in (0, 1]")

    def contains(self, minute_of_run: int) -> bool:
        return self.start_minute <= minute_of_run < self.end_minute


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    seed: int
    start_time: datetime
    duration_minutes: int
    num_merchants: int
    num_drivers: int
    num_customers: int
    base_order_rate_per_minute: float
    """Marketplace-wide mean orders/minute outside any rush-hour window."""
    map_size_km: float
    """Merchants, drivers, and customers are generated within a
    `map_size_km` x `map_size_km` square."""
    avg_driver_speed_kmh: float = 30.0
    driver_speed_stddev_kmh: float = 5.0
    avg_merchant_prep_minutes: float = 12.0
    merchant_prep_stddev_minutes: float = 3.0
    promised_delivery_buffer_minutes: float = 25.0
    """Added on top of the *expected* prep + travel time to set each order's
    promised delivery time — the slack a real ETA algorithm would build in."""
    tick_minutes: int = 1
    max_wait_for_driver_minutes: float = 15.0
    """If no driver is assigned within this long after confirmation, the
    order is cancelled (NO_DRIVER_AVAILABLE) rather than left pending forever."""
    driver_offline_probability_per_tick: float = 0.0008
    """Small per-tick hazard that an assigned driver goes offline mid-delivery,
    scaled by (1 - driver.reliability_score); see `engine.py`."""
    merchant_stockout_probability: float = 0.03
    """Base probability a confirmed order is cancelled for MERCHANT_OUT_OF_STOCK,
    scaled by (1 - merchant.reliability_score)."""
    customer_unreachable_probability: float = 0.02
    """Base probability a delivered-to customer is unreachable, scaled by
    (1 - customer.reachability_score)."""
    perishable_spoilage_probability_per_tick: float = 0.05
    """Per-tick hazard applied only to perishable orders that are already
    running past their promised delivery time while en route to the
    customer — models food spoiling the longer an already-late delivery drags on."""
    rush_hour_windows: tuple[RushHourWindow, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        positive_int_fields = {
            "duration_minutes": self.duration_minutes,
            "num_merchants": self.num_merchants,
            "num_drivers": self.num_drivers,
            "num_customers": self.num_customers,
            "tick_minutes": self.tick_minutes,
        }
        for name, value in positive_int_fields.items():
            if value <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")

        positive_float_fields = {
            "base_order_rate_per_minute": self.base_order_rate_per_minute,
            "map_size_km": self.map_size_km,
            "avg_driver_speed_kmh": self.avg_driver_speed_kmh,
            "avg_merchant_prep_minutes": self.avg_merchant_prep_minutes,
            "promised_delivery_buffer_minutes": self.promised_delivery_buffer_minutes,
        }
        for name, value in positive_float_fields.items():
            if value <= 0:
                raise ValueError(f"{name} must be > 0, got {value}")

        probability_fields = {
            "driver_offline_probability_per_tick": self.driver_offline_probability_per_tick,
            "merchant_stockout_probability": self.merchant_stockout_probability,
            "customer_unreachable_probability": self.customer_unreachable_probability,
            "perishable_spoilage_probability_per_tick": (
                self.perishable_spoilage_probability_per_tick
            ),
        }
        for name, value in probability_fields.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be in [0, 1], got {value}")

        if self.duration_minutes % self.tick_minutes != 0:
            raise ValueError("duration_minutes must be a multiple of tick_minutes")

    def demand_multiplier_at(self, minute_of_run: int) -> float:
        for window in self.rush_hour_windows:
            if window.contains(minute_of_run):
                return window.demand_multiplier
        return 1.0

    def speed_multiplier_at(self, minute_of_run: int) -> float:
        for window in self.rush_hour_windows:
            if window.contains(minute_of_run):
                return window.speed_multiplier
        return 1.0

    def is_rush_hour_at(self, minute_of_run: int) -> bool:
        return any(window.contains(minute_of_run) for window in self.rush_hour_windows)
