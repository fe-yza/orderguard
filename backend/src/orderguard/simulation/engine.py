"""Discrete-time simulation engine.

Design: fixed-size ticks (default 1 simulated minute) rather than a
priority-queue / next-event-time engine. This is the "simplest correct
implementation first" choice from `docs/architecture.md` — a tick-based loop
is far easier to reason about and test, and the entity counts this project
targets (up to 100,000 deliveries, not 100,000 *concurrently active* ones at
any single tick) make per-tick iteration cheap. If Milestone 8 benchmarks show
otherwise, that's the point at which switching to an event-queue engine would
be proposed, with the measured evidence to justify it.

Ground truth vs. prediction: every random draw in this file is *causal* —
scaled by an entity's observable attributes (reliability, backlog, lateness)
so the outcome distribution is realistic. This is the hidden ground truth the
risk engine (Milestone 3) must predict *without* reading any of these rolls or
probabilities — it only ever sees the same state this engine exposes on
`Order`, `Delivery`, `Merchant`, and `Driver` (status, elapsed time, backlog,
idle time, distance remaining). Feeding the risk engine these probabilities
directly would make its predictions meaningless.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta

from orderguard.domain.customer import Customer
from orderguard.domain.delivery import Delivery
from orderguard.domain.driver import Driver
from orderguard.domain.enums import (
    CancellationReason,
    DriverStatus,
    EventType,
    FailureReason,
    OrderStatus,
)
from orderguard.domain.events import DeliveryEvent
from orderguard.domain.geo import Point
from orderguard.domain.merchant import Merchant
from orderguard.domain.order import Order
from orderguard.events.bus import EventBus
from orderguard.simulation.clock import SimClock
from orderguard.simulation.config import SimulationConfig
from orderguard.simulation.generators import (
    generate_customers,
    generate_drivers,
    generate_merchants,
    sample_poisson,
)
from orderguard.simulation.run import SimulationRun

logger = logging.getLogger(__name__)

# Orders of this size or larger get the perishable-spoilage hazard applied.
_PERISHABLE_PROBABILITY = 0.3


class SimulationEngine:
    def __init__(self, config: SimulationConfig, event_bus: EventBus | None = None) -> None:
        self.config = config
        self.event_bus = event_bus
        self.rng = random.Random(config.seed)
        self.clock = SimClock(start_time=config.start_time)

        self.merchants: dict[str, Merchant] = {
            m.id: m for m in generate_merchants(config, self.rng)
        }
        self.drivers: dict[str, Driver] = {d.id: d for d in generate_drivers(config, self.rng)}
        self.customers: dict[str, Customer] = {
            c.id: c for c in generate_customers(config, self.rng)
        }
        self.orders: dict[str, Order] = {}
        self.deliveries: dict[str, Delivery] = {}
        self.events: list[DeliveryEvent] = []

        self._order_counter = 0
        self._awaiting_assignment: list[str] = []  # order_ids, FIFO
        self._confirmed_at: dict[str, datetime] = {}
        self._prep_remaining_minutes: dict[str, float] = {}
        self._en_route_to_merchant: set[str] = set()
        self._at_merchant_waiting: set[str] = set()
        self._en_route_to_customer: set[str] = set()

        self._merchant_list = list(self.merchants.values())
        self._customer_list = list(self.customers.values())

        self._risk_multiplier: dict[str, float] = {}

    # -- intervention feedback ---------------------------------------------

    def apply_intervention_effect(self, order_id: str, probability_reduction: float) -> None:
        """Feed an applied intervention's effect back into the ground-truth
        hazards for this order — this is what makes the experiment
        framework's strategies (Milestone 5) actually diverge, rather than
        computing risk/interventions on the side without them ever changing
        an outcome. `probability_reduction` (from
        `interventions/engine.py`'s catalog) scales down every subsequent
        per-tick hazard roll for this order, and proportionally extends how
        long it's allowed to wait for a driver before being cancelled. The
        *strongest* reduction seen for an order wins (min of multipliers),
        so a later, weaker intervention can't undo an earlier strong one.
        """
        if probability_reduction <= 0:
            return
        multiplier = 1 - probability_reduction
        self._risk_multiplier[order_id] = min(
            self._risk_multiplier.get(order_id, 1.0), multiplier
        )

    def _hazard_multiplier(self, order_id: str) -> float:
        return self._risk_multiplier.get(order_id, 1.0)

    # -- public API ---------------------------------------------------

    def run(self) -> SimulationRun:
        started_at = self.clock.current_time
        num_ticks = self.config.duration_minutes // self.config.tick_minutes
        for _ in range(num_ticks):
            self._tick()
        return SimulationRun(
            id=f"run-{uuid.UUID(int=self.rng.getrandbits(128), version=4)}",
            config=self.config,
            started_at=started_at,
            completed_at=self.clock.current_time,
            merchants=self.merchants,
            drivers=self.drivers,
            customers=self.customers,
            orders=self.orders,
            deliveries=self.deliveries,
            events=self.events,
        )

    # -- per-tick pipeline ---------------------------------------------

    def _tick(self) -> None:
        minute_of_run = self.clock.minute_of_run
        self._spawn_orders(minute_of_run)
        self._expire_unassigned_orders()
        self._assign_drivers(minute_of_run)
        self._apply_hazards(minute_of_run)
        self._advance_prep()
        self._advance_travel_to_merchant(minute_of_run)
        self._advance_travel_to_customer(minute_of_run)
        self.clock.advance(self.config.tick_minutes)

    def _record(self, order: Order, event_type: EventType, **details: object) -> None:
        event = DeliveryEvent(
            delivery_id=self.deliveries[order.id].id if order.id in self.deliveries else "",
            order_id=order.id,
            event_type=event_type,
            occurred_at=self.clock.current_time,
            details=details,
        )
        self.events.append(event)
        if order.id in self.deliveries:
            self.deliveries[order.id].record(event)
        if self.event_bus is not None:
            self.event_bus.publish(event)

    def _release_merchant_capacity(self, order: Order) -> None:
        """Call exactly once per order, when it stops occupying merchant prep
        capacity (picked up, or abandoned beforehand)."""
        if self._prep_remaining_minutes.pop(order.id, None) is not None:
            self.merchants[order.merchant_id].active_order_backlog -= 1

    # -- order arrival ---------------------------------------------------

    def _spawn_orders(self, minute_of_run: int) -> None:
        expected = (
            self.config.base_order_rate_per_minute
            * self.config.tick_minutes
            * self.config.demand_multiplier_at(minute_of_run)
        )
        count = sample_poisson(self.rng, expected)
        for _ in range(count):
            self._create_order()

    def _create_order(self) -> None:
        merchant = self.rng.choice(self._merchant_list)
        customer = self.rng.choice(self._customer_list)
        now = self.clock.current_time

        is_rush_hour = self.config.is_rush_hour_at(self.clock.minute_of_run)
        expected_prep = merchant.expected_prep_minutes(is_rush_hour=is_rush_hour)
        travel_estimate_minutes = (
            merchant.location.distance_to(customer.location) / self.config.avg_driver_speed_kmh
        ) * 60

        order_id = f"order-{self._order_counter:06d}"
        self._order_counter += 1

        order = Order(
            id=order_id,
            merchant_id=merchant.id,
            customer_id=customer.id,
            created_at=now,
            promised_delivery_time=now
            + _minutes(
                expected_prep
                + travel_estimate_minutes
                + self.config.promised_delivery_buffer_minutes
            ),
            item_count=self.rng.randint(1, 5),
            is_perishable=self.rng.random() < _PERISHABLE_PROBABILITY,
        )
        self.orders[order.id] = order
        self._record(order, EventType.ORDER_CREATED)

        order.transition_to(OrderStatus.CONFIRMED, at=now)
        self._record(order, EventType.ORDER_CONFIRMED)

        stockout_probability = self.config.merchant_stockout_probability * (
            1 - merchant.reliability_score
        )
        if self.rng.random() < stockout_probability:
            order.transition_to(
                OrderStatus.CANCELLED,
                at=now,
                cancellation_reason=CancellationReason.MERCHANT_OUT_OF_STOCK,
            )
            self._record(order, EventType.ORDER_CANCELLED, reason="merchant_out_of_stock")
            return

        merchant.active_order_backlog += 1
        self._prep_remaining_minutes[order.id] = max(
            1.0, self.rng.gauss(expected_prep, merchant.prep_time_stddev_minutes)
        )
        self._awaiting_assignment.append(order.id)
        self._confirmed_at[order.id] = now

    def _expire_unassigned_orders(self) -> None:
        still_waiting = []
        for order_id in self._awaiting_assignment:
            order = self.orders[order_id]
            waited_minutes = (
                self.clock.current_time - self._confirmed_at[order_id]
            ).total_seconds() / 60
            effective_max_wait = (
                self.config.max_wait_for_driver_minutes / self._hazard_multiplier(order_id)
            )
            if waited_minutes >= effective_max_wait:
                order.transition_to(
                    OrderStatus.CANCELLED,
                    at=self.clock.current_time,
                    cancellation_reason=CancellationReason.NO_DRIVER_AVAILABLE,
                )
                self._record(order, EventType.ORDER_CANCELLED, reason="no_driver_available")
                self._release_merchant_capacity(order)
                self._confirmed_at.pop(order_id, None)
            else:
                still_waiting.append(order_id)
        self._awaiting_assignment = still_waiting

    # -- driver assignment -------------------------------------------------

    def _assign_drivers(self, minute_of_run: int) -> None:
        if not self._awaiting_assignment:
            return
        still_waiting = []
        for order_id in self._awaiting_assignment:
            order = self.orders[order_id]
            merchant = self.merchants[order.merchant_id]
            driver = self._nearest_available_driver(merchant.location)
            if driver is None:
                still_waiting.append(order_id)
                continue

            now = self.clock.current_time
            delivery = Delivery(
                id=f"delivery-{order.id}",
                order_id=order.id,
                driver_id=driver.id,
                merchant_id=order.merchant_id,
                customer_id=order.customer_id,
                assigned_at=now,
            )
            self.deliveries[order.id] = delivery

            driver.status = DriverStatus.EN_ROUTE
            driver.current_delivery_id = delivery.id
            driver.idle_minutes = 0.0

            order.transition_to(OrderStatus.ASSIGNED, at=now)
            self._record(order, EventType.DRIVER_ASSIGNED, driver_id=driver.id)

            order.transition_to(OrderStatus.EN_ROUTE_TO_MERCHANT, at=now)
            self._record(order, EventType.DRIVER_EN_ROUTE_TO_MERCHANT)
            self._en_route_to_merchant.add(order.id)
            self._confirmed_at.pop(order_id, None)
        self._awaiting_assignment = still_waiting

    def _nearest_available_driver(self, near: Point) -> Driver | None:
        available = [d for d in self.drivers.values() if d.is_available]
        if not available:
            return None
        return min(available, key=lambda d: d.location.distance_to(near))

    # -- hazards (offline drivers, spoilage, unreachable customers) --------

    def _apply_hazards(self, minute_of_run: int) -> None:
        active_before_pickup = self._en_route_to_merchant | self._at_merchant_waiting
        for order_id in list(active_before_pickup):
            self._maybe_driver_goes_offline(order_id, failure_reason=FailureReason.NEVER_PICKED_UP)

        for order_id in list(self._en_route_to_customer):
            if order_id not in self.orders:
                continue
            self._maybe_driver_goes_offline(
                order_id, failure_reason=FailureReason.DRIVER_NEVER_ARRIVED
            )

        for order_id in list(self._en_route_to_customer):
            if order_id not in self.orders:
                continue
            self._maybe_spoil(order_id)

    def _maybe_driver_goes_offline(self, order_id: str, *, failure_reason: FailureReason) -> None:
        order = self.orders.get(order_id)
        if order is None or order.is_terminal:
            return
        delivery = self.deliveries[order_id]
        driver = self.drivers[delivery.driver_id]
        probability = (
            self.config.driver_offline_probability_per_tick
            * (1 - driver.reliability_score)
            * self._hazard_multiplier(order_id)
        )
        if self.rng.random() >= probability:
            return

        now = self.clock.current_time
        order.transition_to(OrderStatus.FAILED, at=now, failure_reason=failure_reason)
        self._record(order, EventType.DRIVER_WENT_OFFLINE, driver_id=driver.id)
        self._record(order, EventType.ORDER_FAILED, reason=failure_reason.value)
        self._release_merchant_capacity(order)
        self._en_route_to_merchant.discard(order_id)
        self._at_merchant_waiting.discard(order_id)
        self._en_route_to_customer.discard(order_id)
        driver.status = DriverStatus.OFFLINE
        driver.current_delivery_id = None

    def _maybe_spoil(self, order_id: str) -> None:
        order = self.orders[order_id]
        if not order.is_perishable or order.is_terminal:
            return
        if self.clock.current_time <= order.promised_delivery_time:
            return
        probability = (
            self.config.perishable_spoilage_probability_per_tick
            * self._hazard_multiplier(order_id)
        )
        if self.rng.random() >= probability:
            return

        now = self.clock.current_time
        delivery = self.deliveries[order_id]
        driver = self.drivers[delivery.driver_id]
        order.transition_to(
            OrderStatus.FAILED, at=now, failure_reason=FailureReason.DAMAGED_OR_SPOILED
        )
        self._record(order, EventType.ORDER_FAILED, reason="damaged_or_spoiled")
        self._en_route_to_customer.discard(order_id)
        driver.status = DriverStatus.AVAILABLE
        driver.current_delivery_id = None

    # -- prep and travel progression ---------------------------------------

    def _advance_prep(self) -> None:
        for order_id in list(self._prep_remaining_minutes):
            order = self.orders.get(order_id)
            if order is None or order.is_terminal:
                self._prep_remaining_minutes.pop(order_id, None)
                continue
            self._prep_remaining_minutes[order_id] -= self.config.tick_minutes

            if (
                order_id in self._at_merchant_waiting
                and self._prep_remaining_minutes[order_id] <= 0
            ):
                self._pick_up(order)

    def _advance_travel_to_merchant(self, minute_of_run: int) -> None:
        speed_multiplier = self.config.speed_multiplier_at(minute_of_run)
        for order_id in list(self._en_route_to_merchant):
            order = self.orders[order_id]
            if order.is_terminal:
                self._en_route_to_merchant.discard(order_id)
                continue
            delivery = self.deliveries[order_id]
            driver = self.drivers[delivery.driver_id]
            merchant = self.merchants[order.merchant_id]
            arrived = driver.move_toward(
                merchant.location,
                minutes=self.config.tick_minutes,
                speed_multiplier=speed_multiplier,
            )
            if not arrived:
                continue

            now = self.clock.current_time
            order.transition_to(OrderStatus.ARRIVED_AT_MERCHANT, at=now)
            self._record(order, EventType.DRIVER_ARRIVED_AT_MERCHANT)
            driver.status = DriverStatus.WAITING
            self._en_route_to_merchant.discard(order_id)
            self._at_merchant_waiting.add(order_id)

            if self._prep_remaining_minutes.get(order_id, 1.0) <= 0:
                self._pick_up(order)

    def _pick_up(self, order: Order) -> None:
        now = self.clock.current_time
        delivery = self.deliveries[order.id]
        driver = self.drivers[delivery.driver_id]

        order.transition_to(OrderStatus.PICKED_UP, at=now)
        self._record(order, EventType.ORDER_PICKED_UP)
        self._release_merchant_capacity(order)
        self._at_merchant_waiting.discard(order.id)

        order.transition_to(OrderStatus.EN_ROUTE_TO_CUSTOMER, at=now)
        self._record(order, EventType.DRIVER_EN_ROUTE_TO_CUSTOMER)
        driver.status = DriverStatus.DELIVERING
        self._en_route_to_customer.add(order.id)

    def _advance_travel_to_customer(self, minute_of_run: int) -> None:
        speed_multiplier = self.config.speed_multiplier_at(minute_of_run)
        for order_id in list(self._en_route_to_customer):
            order = self.orders[order_id]
            if order.is_terminal:
                self._en_route_to_customer.discard(order_id)
                continue
            delivery = self.deliveries[order_id]
            driver = self.drivers[delivery.driver_id]
            customer = self.customers[order.customer_id]
            arrived = driver.move_toward(
                customer.location,
                minutes=self.config.tick_minutes,
                speed_multiplier=speed_multiplier,
            )
            if not arrived:
                continue

            now = self.clock.current_time
            unreachable_probability = (
                self.config.customer_unreachable_probability
                * (1 - customer.reachability_score)
                * self._hazard_multiplier(order_id)
            )
            if self.rng.random() < unreachable_probability:
                order.transition_to(
                    OrderStatus.FAILED, at=now, failure_reason=FailureReason.CUSTOMER_UNREACHABLE
                )
                self._record(order, EventType.ORDER_FAILED, reason="customer_unreachable")
            else:
                order.transition_to(OrderStatus.DELIVERED, at=now)
                self._record(order, EventType.ORDER_DELIVERED)

            self._en_route_to_customer.discard(order_id)
            driver.status = DriverStatus.AVAILABLE
            driver.current_delivery_id = None


def _minutes(value: float) -> timedelta:
    return timedelta(minutes=value)
