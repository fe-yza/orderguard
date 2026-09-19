"""Simulation engine throughput benchmark.

Not a pytest test — this produces measurements, not pass/fail assertions.
Run directly: `PYTHONPATH=src .venv/bin/python benchmarks/benchmark_simulation.py`

Targets ~1K / 10K / 100K total orders per Milestone 8's requirement, holding
duration fixed (1440 simulated minutes = 1 day) and scaling the order
arrival rate (and proportionally, driver/merchant/customer counts) to hit
each target. Reports both the bare engine (no risk/intervention wiring) and
the full stack (risk + intervention services attached via the event bus),
since the full stack is what actually runs in production use.
"""

from __future__ import annotations

import time
from datetime import datetime

from orderguard.events.bus import InProcessEventBus
from orderguard.interventions.engine import InterventionEngine
from orderguard.interventions.service import InterventionService
from orderguard.risk.engine import RiskAssessmentService, RiskEngine
from orderguard.simulation.config import SimulationConfig
from orderguard.simulation.engine import SimulationEngine

DURATION_MINUTES = 1440


def make_config(target_orders: int, seed: int = 1) -> SimulationConfig:
    rate = target_orders / DURATION_MINUTES
    return SimulationConfig(
        seed=seed,
        start_time=datetime(2026, 1, 1, 0, 0, 0),
        duration_minutes=DURATION_MINUTES,
        num_merchants=max(5, int(rate * 8)),
        num_drivers=max(10, int(rate * 12)),
        num_customers=max(50, int(rate * 120)),
        base_order_rate_per_minute=rate,
        map_size_km=max(8.0, rate**0.5 * 4),
    )


def run_bare(config: SimulationConfig) -> tuple[float, int, int]:
    engine = SimulationEngine(config)
    t0 = time.perf_counter()
    run = engine.run()
    elapsed = time.perf_counter() - t0
    return elapsed, len(run.orders), len(run.events)


def run_full_stack(config: SimulationConfig) -> tuple[float, int, int]:
    bus = InProcessEventBus()
    engine = SimulationEngine(config, event_bus=bus)
    risk_service = RiskAssessmentService(
        RiskEngine(),
        bus,
        orders=engine.orders,
        merchants=engine.merchants,
        drivers=engine.drivers,
        customers=engine.customers,
        deliveries=engine.deliveries,
        config=config,
        clock=engine.clock,
    )
    InterventionService(
        InterventionEngine(),
        risk_service,
        bus,
        orders=engine.orders,
        deliveries=engine.deliveries,
        on_decision=lambda d: engine.apply_intervention_effect(
            d.order_id, d.chosen_candidate.probability_reduction
        ),
    )
    t0 = time.perf_counter()
    run = engine.run()
    elapsed = time.perf_counter() - t0
    return elapsed, len(run.orders), len(run.events)


def main() -> None:
    print(f"{'target':>10} {'actual':>10} {'events':>10} {'bare_s':>10} {'full_s':>10} "
          f"{'bare_orders/s':>15} {'full_orders/s':>15}")
    for target in (1_000, 10_000, 100_000):
        config = make_config(target)
        bare_elapsed, actual_orders, events = run_bare(config)
        full_elapsed, _, _ = run_full_stack(config)
        print(
            f"{target:>10} {actual_orders:>10} {events:>10} "
            f"{bare_elapsed:>10.3f} {full_elapsed:>10.3f} "
            f"{actual_orders / bare_elapsed:>15.0f} {actual_orders / full_elapsed:>15.0f}"
        )


if __name__ == "__main__":
    main()
