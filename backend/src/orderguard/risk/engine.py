"""Rules-based risk engine.

`RiskEngine.assess` is pure: given a snapshot of *observable* state (order,
merchant, driver, customer, current time, and a couple of environment
values), it returns a `RiskAssessment` with a weighted, explainable factor
breakdown. It never reads the simulation's hidden ground-truth hazard rolls —
only the same state fields a real ops dashboard would have (see
`simulation/engine.py`'s module docstring). This is what makes the
assessment a genuine *prediction* rather than an oracle lookup.

`RiskAssessmentService` is the event-reactive wiring: it subscribes to the
event bus and recomputes an assessment for an order whenever something about
it changes, storing the result. It does not poll — a known consequence
(documented in `docs/interview-notes.md`) is that risk for an order sitting
untouched between two events (e.g. still waiting for a driver) isn't updated
until the next event fires for that order.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from orderguard.domain.customer import Customer
from orderguard.domain.driver import Driver
from orderguard.domain.enums import OrderStatus
from orderguard.domain.events import DeliveryEvent
from orderguard.domain.merchant import Merchant
from orderguard.domain.order import Order
from orderguard.events.bus import EventBus
from orderguard.risk.models import PredictedFailureType, RiskAssessment, RiskFactor


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# Rule name -> (max weight, mapped predicted-failure type when it dominates).
_RULE_WEIGHTS: dict[str, float] = {
    "lateness_projection": 35.0,
    "merchant_backlog": 15.0,
    "driver_unassigned_wait": 15.0,
    "driver_reliability": 10.0,
    "merchant_reliability": 10.0,
    "customer_reachability": 10.0,
    "perishable_overdue": 5.0,
}


class RiskEngine:
    """Stateless rule evaluator. Thresholds are constructor params, not
    magic numbers in the rule bodies, per `docs/architecture.md`."""

    def __init__(
        self,
        *,
        weights: dict[str, float] | None = None,
        lateness_scale_minutes: float = 20.0,
        backlog_scale: float = 8.0,
        risk_threshold_for_prediction: float = 15.0,
    ) -> None:
        self.weights = dict(_RULE_WEIGHTS if weights is None else weights)
        self.lateness_scale_minutes = lateness_scale_minutes
        self.backlog_scale = backlog_scale
        self.risk_threshold_for_prediction = risk_threshold_for_prediction

    def assess(
        self,
        order: Order,
        *,
        merchant: Merchant,
        customer: Customer,
        driver: Driver | None,
        now: datetime,
        is_rush_hour: bool,
        travel_speed_multiplier: float,
        avg_driver_speed_kmh: float,
        waited_for_driver_minutes: float | None,
        max_wait_for_driver_minutes: float,
        delivery_id: str | None,
    ) -> RiskAssessment:
        if order.is_terminal:
            return self._terminal_assessment(order, delivery_id, now)

        remaining_prep = self._remaining_prep_minutes(order, merchant, now, is_rush_hour)
        remaining_travel = self._remaining_travel_minutes(
            order, merchant, customer, driver, avg_driver_speed_kmh, travel_speed_multiplier
        )
        estimated_completion = now + timedelta(minutes=remaining_prep + remaining_travel)
        predicted_delay_minutes = (
            estimated_completion - order.promised_delivery_time
        ).total_seconds() / 60

        factors: list[RiskFactor] = []
        pre_pickup = order.status not in (
            OrderStatus.PICKED_UP,
            OrderStatus.EN_ROUTE_TO_CUSTOMER,
        )

        factors.append(
            RiskFactor(
                name="lateness_projection",
                description=(
                    "Projected completion time vs. the promised delivery time, "
                    "given current prep and travel progress."
                ),
                weight=self.weights["lateness_projection"],
                raw_signal=(
                    signal := _clamp01(predicted_delay_minutes / self.lateness_scale_minutes)
                ),
                contribution=self.weights["lateness_projection"] * signal,
            )
        )

        if pre_pickup:
            factors.append(
                RiskFactor(
                    name="merchant_backlog",
                    description="How many orders the merchant is currently juggling.",
                    weight=self.weights["merchant_backlog"],
                    raw_signal=(
                        signal := _clamp01(merchant.active_order_backlog / self.backlog_scale)
                    ),
                    contribution=self.weights["merchant_backlog"] * signal,
                )
            )
            factors.append(
                RiskFactor(
                    name="merchant_reliability",
                    description="Merchant's historical reliability score (lower = riskier).",
                    weight=self.weights["merchant_reliability"],
                    raw_signal=(signal := _clamp01(1 - merchant.reliability_score)),
                    contribution=self.weights["merchant_reliability"] * signal,
                )
            )

        if driver is None and waited_for_driver_minutes is not None:
            factors.append(
                RiskFactor(
                    name="driver_unassigned_wait",
                    description="How long this order has waited for a driver to be assigned.",
                    weight=self.weights["driver_unassigned_wait"],
                    raw_signal=(
                        signal := _clamp01(
                            waited_for_driver_minutes / max_wait_for_driver_minutes
                        )
                    ),
                    contribution=self.weights["driver_unassigned_wait"] * signal,
                )
            )

        if driver is not None:
            factors.append(
                RiskFactor(
                    name="driver_reliability",
                    description="Assigned driver's historical reliability score.",
                    weight=self.weights["driver_reliability"],
                    raw_signal=(signal := _clamp01(1 - driver.reliability_score)),
                    contribution=self.weights["driver_reliability"] * signal,
                )
            )

        if order.status in (OrderStatus.PICKED_UP, OrderStatus.EN_ROUTE_TO_CUSTOMER):
            factors.append(
                RiskFactor(
                    name="customer_reachability",
                    description="Customer's historical reachability score at the door.",
                    weight=self.weights["customer_reachability"],
                    raw_signal=(signal := _clamp01(1 - customer.reachability_score)),
                    contribution=self.weights["customer_reachability"] * signal,
                )
            )

        if order.is_perishable and order.status == OrderStatus.EN_ROUTE_TO_CUSTOMER:
            factors.append(
                RiskFactor(
                    name="perishable_overdue",
                    description="Perishable order already past its promised delivery time.",
                    weight=self.weights["perishable_overdue"],
                    raw_signal=(signal := 1.0 if now > order.promised_delivery_time else 0.0),
                    contribution=self.weights["perishable_overdue"] * signal,
                )
            )

        total_weight = sum(f.weight for f in factors)
        overall_risk_score = (
            0.0
            if total_weight == 0
            else sum(f.contribution for f in factors) / total_weight * 100
        )
        confidence = max(0.3, min(0.95, 0.3 + 0.12 * len(factors)))
        predicted_failure_type = self._predict_failure_type(overall_risk_score, factors, order)

        return RiskAssessment(
            id=f"risk-{uuid.uuid4()}",
            order_id=order.id,
            delivery_id=delivery_id,
            computed_at=now,
            overall_risk_score=overall_risk_score,
            predicted_failure_type=predicted_failure_type,
            confidence=confidence,
            predicted_delay_minutes=predicted_delay_minutes,
            factors=factors,
        )

    def _terminal_assessment(
        self, order: Order, delivery_id: str | None, now: datetime
    ) -> RiskAssessment:
        delay = 0.0
        if order.status == OrderStatus.DELIVERED and order.delivered_at is not None:
            delay = (order.delivered_at - order.promised_delivery_time).total_seconds() / 60
        return RiskAssessment(
            id=f"risk-{uuid.uuid4()}",
            order_id=order.id,
            delivery_id=delivery_id,
            computed_at=now,
            overall_risk_score=0.0,
            predicted_failure_type=None,
            confidence=1.0,
            predicted_delay_minutes=delay,
            factors=[],
        )

    def _remaining_prep_minutes(
        self, order: Order, merchant: Merchant, now: datetime, is_rush_hour: bool
    ) -> float:
        if order.status in (OrderStatus.PICKED_UP, OrderStatus.EN_ROUTE_TO_CUSTOMER):
            return 0.0
        expected_total = merchant.expected_prep_minutes(is_rush_hour=is_rush_hour)
        elapsed = max(0.0, (now - order.created_at).total_seconds() / 60)
        return max(0.0, expected_total - elapsed)

    def _remaining_travel_minutes(
        self,
        order: Order,
        merchant: Merchant,
        customer: Customer,
        driver: Driver | None,
        avg_driver_speed_kmh: float,
        travel_speed_multiplier: float,
    ) -> float:
        effective_speed = max(1.0, avg_driver_speed_kmh * travel_speed_multiplier)
        if driver is None:
            distance = merchant.location.distance_to(customer.location)
            return (distance / effective_speed) * 60

        if order.status == OrderStatus.EN_ROUTE_TO_CUSTOMER:
            distance = driver.location.distance_to(customer.location)
        else:
            distance_to_merchant = driver.location.distance_to(merchant.location)
            distance_merchant_to_customer = merchant.location.distance_to(customer.location)
            distance = distance_to_merchant + distance_merchant_to_customer
        return (distance / effective_speed) * 60

    def _predict_failure_type(
        self, overall_risk_score: float, factors: list[RiskFactor], order: Order
    ) -> PredictedFailureType | None:
        if overall_risk_score < self.risk_threshold_for_prediction or not factors:
            return None
        dominant = max(factors, key=lambda f: f.contribution)
        if dominant.contribution <= 0:
            return None

        mapping = {
            "lateness_projection": PredictedFailureType.LATE_DELIVERY,
            "merchant_backlog": PredictedFailureType.NEVER_PICKED_UP,
            "merchant_reliability": PredictedFailureType.NEVER_PICKED_UP,
            "driver_unassigned_wait": PredictedFailureType.NO_DRIVER_AVAILABLE,
            "customer_reachability": PredictedFailureType.CUSTOMER_UNREACHABLE,
            "perishable_overdue": PredictedFailureType.DAMAGED_OR_SPOILED,
        }
        if dominant.name == "driver_reliability":
            return (
                PredictedFailureType.DRIVER_NEVER_ARRIVED
                if order.status in (OrderStatus.PICKED_UP, OrderStatus.EN_ROUTE_TO_CUSTOMER)
                else PredictedFailureType.NEVER_PICKED_UP
            )
        return mapping.get(dominant.name)


class RiskAssessmentService:
    """Subscribes a `RiskEngine` to a live simulation's event bus and keeps
    the latest assessment per order. Holds read-only references into the
    simulation engine's live dicts — it never mutates them."""

    def __init__(
        self,
        risk_engine: RiskEngine,
        event_bus: EventBus,
        *,
        orders: dict[str, Order],
        merchants: dict[str, Merchant],
        drivers: dict[str, Driver],
        customers: dict[str, Customer],
        deliveries: dict,
        config,
        clock,
    ) -> None:
        self.risk_engine = risk_engine
        self._orders = orders
        self._merchants = merchants
        self._drivers = drivers
        self._customers = customers
        self._deliveries = deliveries
        self._config = config
        self._clock = clock
        self.latest_assessment: dict[str, RiskAssessment] = {}
        self.history: dict[str, list[RiskAssessment]] = {}
        event_bus.subscribe(self._on_event)

    def _on_event(self, event: DeliveryEvent) -> None:
        order = self._orders.get(event.order_id)
        if order is None:
            return

        merchant = self._merchants[order.merchant_id]
        customer = self._customers[order.customer_id]
        delivery = self._deliveries.get(order.id)
        driver = self._drivers[delivery.driver_id] if delivery is not None else None

        now = self._clock.current_time
        minute_of_run = self._clock.minute_of_run
        waited_for_driver_minutes = None
        if driver is None and order.status == OrderStatus.CONFIRMED:
            waited_for_driver_minutes = (now - order.created_at).total_seconds() / 60

        assessment = self.risk_engine.assess(
            order,
            merchant=merchant,
            customer=customer,
            driver=driver,
            now=now,
            is_rush_hour=self._config.is_rush_hour_at(minute_of_run),
            travel_speed_multiplier=self._config.speed_multiplier_at(minute_of_run),
            avg_driver_speed_kmh=self._config.avg_driver_speed_kmh,
            waited_for_driver_minutes=waited_for_driver_minutes,
            max_wait_for_driver_minutes=self._config.max_wait_for_driver_minutes,
            delivery_id=delivery.id if delivery is not None else None,
        )
        self.latest_assessment[order.id] = assessment
        self.history.setdefault(order.id, []).append(assessment)
