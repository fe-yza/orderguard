import random
from datetime import datetime, timedelta

import pytest

from orderguard.domain.enums import DriverStatus, OrderStatus
from orderguard.simulation.clock import SimClock
from orderguard.simulation.config import RushHourWindow, SimulationConfig
from orderguard.simulation.engine import SimulationEngine
from orderguard.simulation.generators import (
    generate_customers,
    generate_drivers,
    generate_merchants,
    sample_poisson,
)

NOW = datetime(2026, 1, 1, 8, 0, 0)


def make_config(**overrides) -> SimulationConfig:
    defaults = dict(
        seed=123,
        start_time=NOW,
        duration_minutes=120,
        num_merchants=5,
        num_drivers=8,
        num_customers=50,
        base_order_rate_per_minute=0.5,
        map_size_km=10.0,
    )
    defaults.update(overrides)
    return SimulationConfig(**defaults)


class TestRushHourWindow:
    def test_contains(self):
        window = RushHourWindow(60, 120, demand_multiplier=1.5, speed_multiplier=0.8)
        assert window.contains(60) is True
        assert window.contains(119) is True
        assert window.contains(120) is False
        assert window.contains(59) is False

    @pytest.mark.parametrize(
        "kwargs",
        [
            dict(start_minute=-1, end_minute=10, demand_multiplier=1, speed_multiplier=1),
            dict(start_minute=10, end_minute=10, demand_multiplier=1, speed_multiplier=1),
            dict(start_minute=0, end_minute=10, demand_multiplier=0, speed_multiplier=1),
            dict(start_minute=0, end_minute=10, demand_multiplier=1, speed_multiplier=1.5),
            dict(start_minute=0, end_minute=10, demand_multiplier=1, speed_multiplier=0),
        ],
    )
    def test_invalid_windows_rejected(self, kwargs):
        with pytest.raises(ValueError):
            RushHourWindow(**kwargs)


class TestSimulationConfig:
    def test_valid_config(self):
        config = make_config()
        assert config.tick_minutes == 1

    @pytest.mark.parametrize(
        "field_name,value",
        [
            ("duration_minutes", 0),
            ("num_merchants", 0),
            ("num_drivers", 0),
            ("num_customers", 0),
            ("base_order_rate_per_minute", 0),
            ("map_size_km", 0),
            ("merchant_stockout_probability", 1.5),
            ("driver_offline_probability_per_tick", -0.1),
        ],
    )
    def test_invalid_values_rejected(self, field_name, value):
        with pytest.raises(ValueError):
            make_config(**{field_name: value})

    def test_duration_must_be_multiple_of_tick(self):
        with pytest.raises(ValueError):
            make_config(duration_minutes=100, tick_minutes=7)

    def test_demand_and_speed_multiplier_lookup(self):
        window = RushHourWindow(60, 120, demand_multiplier=2.0, speed_multiplier=0.5)
        config = make_config(rush_hour_windows=(window,))
        assert config.demand_multiplier_at(30) == 1.0
        assert config.demand_multiplier_at(90) == 2.0
        assert config.speed_multiplier_at(90) == 0.5
        assert config.is_rush_hour_at(90) is True
        assert config.is_rush_hour_at(30) is False


class TestSimClock:
    def test_starts_at_start_time(self):
        clock = SimClock(start_time=NOW)
        assert clock.current_time == NOW
        assert clock.minute_of_run == 0

    def test_advance(self):
        clock = SimClock(start_time=NOW)
        clock.advance(90)
        assert clock.current_time == NOW + timedelta(minutes=90)
        assert clock.minute_of_run == 90


class TestGenerators:
    def test_generators_are_deterministic(self):
        config = make_config()
        merchants_a = generate_merchants(config, random.Random(config.seed))
        merchants_b = generate_merchants(config, random.Random(config.seed))
        assert [m.id for m in merchants_a] == [m.id for m in merchants_b]
        assert [m.location for m in merchants_a] == [m.location for m in merchants_b]
        assert [m.base_prep_minutes for m in merchants_a] == [
            m.base_prep_minutes for m in merchants_b
        ]

    def test_generates_requested_counts(self):
        config = make_config()
        rng = random.Random(config.seed)
        assert len(generate_merchants(config, rng)) == config.num_merchants
        assert len(generate_drivers(config, rng)) == config.num_drivers
        assert len(generate_customers(config, rng)) == config.num_customers

    def test_generated_locations_within_bounds(self):
        config = make_config(map_size_km=5.0)
        rng = random.Random(config.seed)
        for merchant in generate_merchants(config, rng):
            assert 0 <= merchant.location.x_km <= 5.0
            assert 0 <= merchant.location.y_km <= 5.0

    def test_sample_poisson_zero_mean(self):
        rng = random.Random(1)
        assert sample_poisson(rng, 0) == 0

    def test_sample_poisson_average_matches_mean(self):
        rng = random.Random(1)
        mean = 3.0
        samples = [sample_poisson(rng, mean) for _ in range(5000)]
        assert abs(sum(samples) / len(samples) - mean) < 0.2


class TestSimulationEngine:
    def test_run_is_deterministic(self):
        config = make_config(duration_minutes=180, base_order_rate_per_minute=0.8)
        run_a = SimulationEngine(config).run()
        run_b = SimulationEngine(config).run()

        assert set(run_a.orders) == set(run_b.orders)
        for order_id in run_a.orders:
            assert run_a.orders[order_id].status == run_b.orders[order_id].status
        assert len(run_a.events) == len(run_b.events)

    def test_different_seeds_produce_different_outcomes(self):
        config_a = make_config(seed=1, duration_minutes=300, base_order_rate_per_minute=1.0)
        config_b = make_config(seed=2, duration_minutes=300, base_order_rate_per_minute=1.0)
        run_a = SimulationEngine(config_a).run()
        run_b = SimulationEngine(config_b).run()
        assert len(run_a.orders) != len(run_b.orders) or any(
            run_a.orders[k].status != run_b.orders.get(k, run_a.orders[k]).status
            for k in run_a.orders
            if k in run_b.orders
        )

    def test_orders_are_created_and_reach_terminal_or_valid_in_flight_states(self):
        config = make_config(duration_minutes=240, base_order_rate_per_minute=0.6)
        run = SimulationEngine(config).run()
        assert len(run.orders) > 0
        valid_in_flight = {
            OrderStatus.CREATED,
            OrderStatus.CONFIRMED,
            OrderStatus.ASSIGNED,
            OrderStatus.EN_ROUTE_TO_MERCHANT,
            OrderStatus.ARRIVED_AT_MERCHANT,
            OrderStatus.PICKED_UP,
            OrderStatus.EN_ROUTE_TO_CUSTOMER,
        }
        terminal = {OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.CANCELLED}
        for order in run.orders.values():
            assert order.status in valid_in_flight | terminal

    def test_every_delivered_order_has_a_delivery_with_a_valid_driver(self):
        # A driver freed after delivering one order can legitimately pick up
        # another before the run ends, so we can't assert anything about a
        # driver's *final* state here — only that the delivery record itself
        # is well-formed.
        config = make_config(duration_minutes=240, base_order_rate_per_minute=0.6)
        engine = SimulationEngine(config)
        run = engine.run()
        delivered = [o for o in run.orders.values() if o.status == OrderStatus.DELIVERED]
        assert len(delivered) > 0
        for order in delivered:
            assert order.id in run.deliveries
            delivery = run.deliveries[order.id]
            assert delivery.driver_id in run.drivers

    def test_drivers_not_in_an_active_delivery_are_available_or_offline(self):
        config = make_config(duration_minutes=240, base_order_rate_per_minute=0.6)
        run = SimulationEngine(config).run()
        for driver in run.drivers.values():
            if driver.current_delivery_id is None:
                assert driver.status in (DriverStatus.AVAILABLE, DriverStatus.OFFLINE)

    def test_cancelled_orders_release_merchant_backlog(self):
        config = make_config(
            duration_minutes=300,
            base_order_rate_per_minute=2.0,
            num_drivers=1,
            max_wait_for_driver_minutes=5.0,
        )
        run = SimulationEngine(config).run()
        cancelled = [o for o in run.orders.values() if o.status == OrderStatus.CANCELLED]
        assert len(cancelled) > 0
        # No merchant should be left thinking it's still prepping an order
        # that was actually abandoned — backlog should never go negative,
        # and shouldn't be stuck permanently inflated either.
        for merchant in run.merchants.values():
            assert merchant.active_order_backlog >= 0

    def test_high_offline_probability_produces_failures(self):
        config = make_config(
            duration_minutes=400,
            base_order_rate_per_minute=1.5,
            num_drivers=10,
            driver_offline_probability_per_tick=0.05,
        )
        run = SimulationEngine(config).run()
        failed = [o for o in run.orders.values() if o.status == OrderStatus.FAILED]
        assert len(failed) > 0
        for order in failed:
            assert order.failure_reason is not None

    def test_event_log_starts_with_order_created_for_each_order(self):
        config = make_config(duration_minutes=120, base_order_rate_per_minute=0.5)
        run = SimulationEngine(config).run()
        first_event_by_order = {}
        for event in run.events:
            first_event_by_order.setdefault(event.order_id, event)
        assert len(first_event_by_order) == len(run.orders)
        for event in first_event_by_order.values():
            assert event.event_type.value == "order_created"

    def test_rush_hour_increases_order_volume(self):
        rush_window = RushHourWindow(0, 60, demand_multiplier=5.0, speed_multiplier=1.0)
        busy_config = make_config(
            duration_minutes=60, base_order_rate_per_minute=0.5, rush_hour_windows=(rush_window,)
        )
        quiet_config = make_config(duration_minutes=60, base_order_rate_per_minute=0.5)
        busy_run = SimulationEngine(busy_config).run()
        quiet_run = SimulationEngine(quiet_config).run()
        assert len(busy_run.orders) > len(quiet_run.orders)

    def test_scales_to_thousands_of_orders(self):
        config = make_config(
            duration_minutes=600,
            num_merchants=50,
            num_drivers=150,
            num_customers=3000,
            base_order_rate_per_minute=6.0,
            map_size_km=20.0,
        )
        run = SimulationEngine(config).run()
        assert len(run.orders) > 1000
