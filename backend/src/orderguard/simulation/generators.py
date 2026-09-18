"""Deterministic population generation.

Every random draw here goes through the single `random.Random` instance the
engine owns (seeded from `SimulationConfig.seed`) — nothing in this module
touches the global `random` module. Same seed + same config always produces
byte-identical merchants, drivers, and customers, which the experiment
framework (Milestone 5) depends on to compare strategies fairly.

IDs are sequential and human-readable (`merchant-0001`) rather than random
UUIDs — UUIDs would either need their own seeded source (extra complexity)
or would break determinism if generated from OS entropy, for no benefit.
"""

from __future__ import annotations

import random

from orderguard.domain.customer import Customer
from orderguard.domain.driver import Driver
from orderguard.domain.geo import Point
from orderguard.domain.merchant import Merchant
from orderguard.simulation.config import SimulationConfig


def _random_point(rng: random.Random, map_size_km: float) -> Point:
    return Point(x_km=rng.uniform(0, map_size_km), y_km=rng.uniform(0, map_size_km))


def _bounded_gauss(rng: random.Random, mean: float, stddev: float, *, floor: float) -> float:
    """`random.gauss` can return values below a physical floor (e.g.
    negative prep time) for large stddev — clamp rather than reject-and-retry,
    which keeps generation O(1) per entity."""
    return max(floor, rng.gauss(mean, stddev))


def generate_merchants(config: SimulationConfig, rng: random.Random) -> list[Merchant]:
    merchants = []
    for i in range(config.num_merchants):
        merchants.append(
            Merchant(
                id=f"merchant-{i:04d}",
                name=f"Merchant {i:04d}",
                location=_random_point(rng, config.map_size_km),
                base_prep_minutes=_bounded_gauss(
                    rng,
                    config.avg_merchant_prep_minutes,
                    config.merchant_prep_stddev_minutes,
                    floor=2.0,
                ),
                prep_time_stddev_minutes=max(0.5, rng.gauss(2.0, 0.5)),
                rush_hour_multiplier=rng.uniform(1.2, 2.0),
                reliability_score=min(1.0, max(0.0, rng.gauss(0.93, 0.05))),
            )
        )
    return merchants


def generate_drivers(config: SimulationConfig, rng: random.Random) -> list[Driver]:
    drivers = []
    for i in range(config.num_drivers):
        drivers.append(
            Driver(
                id=f"driver-{i:04d}",
                name=f"Driver {i:04d}",
                location=_random_point(rng, config.map_size_km),
                speed_kmh=_bounded_gauss(
                    rng, config.avg_driver_speed_kmh, config.driver_speed_stddev_kmh, floor=5.0
                ),
                reliability_score=min(1.0, max(0.0, rng.gauss(0.95, 0.04))),
            )
        )
    return drivers


def generate_customers(config: SimulationConfig, rng: random.Random) -> list[Customer]:
    customers = []
    for i in range(config.num_customers):
        customers.append(
            Customer(
                id=f"customer-{i:04d}",
                name=f"Customer {i:04d}",
                location=_random_point(rng, config.map_size_km),
                reachability_score=min(1.0, max(0.0, rng.gauss(0.97, 0.03))),
            )
        )
    return customers


def sample_poisson(rng: random.Random, mean: float) -> int:
    """Knuth's algorithm. Fine for the small means (a handful of orders per
    tick) this simulation deals with; would need a different approach
    (e.g. normal approximation) if `mean` ever got large (>~30), which it
    doesn't at any scale this project targets (see benchmarks, Milestone 8).
    """
    if mean <= 0:
        return 0
    import math

    limit = math.exp(-mean)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= limit:
            return k - 1
