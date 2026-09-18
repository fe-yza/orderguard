from datetime import datetime, timedelta

import pytest

from orderguard.domain.customer import Customer
from orderguard.domain.driver import Driver
from orderguard.domain.enums import CancellationReason, OrderStatus
from orderguard.domain.geo import Point
from orderguard.domain.merchant import Merchant
from orderguard.domain.order import Order
from orderguard.events.bus import InProcessEventBus
from orderguard.risk.engine import RiskAssessmentService, RiskEngine
from orderguard.risk.models import PredictedFailureType
from orderguard.simulation.config import SimulationConfig
from orderguard.simulation.engine import SimulationEngine

NOW = datetime(2026, 1, 1, 12, 0, 0)


def make_order(**overrides) -> Order:
    defaults = dict(
        id="order-1",
        merchant_id="merchant-1",
        customer_id="customer-1",
        created_at=NOW,
        promised_delivery_time=NOW + timedelta(minutes=30),
        item_count=2,
        is_perishable=False,
        status=OrderStatus.CONFIRMED,
    )
    defaults.update(overrides)
    return Order(**defaults)


def make_merchant(**overrides) -> Merchant:
    defaults = dict(
        id="merchant-1",
        name="M",
        location=Point(0, 0),
        base_prep_minutes=10,
        prep_time_stddev_minutes=2,
        rush_hour_multiplier=1.5,
        reliability_score=0.95,
    )
    defaults.update(overrides)
    return Merchant(**defaults)


def make_customer(**overrides) -> Customer:
    defaults = dict(id="customer-1", name="C", location=Point(5, 0), reachability_score=0.95)
    defaults.update(overrides)
    return Customer(**defaults)


def make_driver(**overrides) -> Driver:
    defaults = dict(
        id="driver-1", name="D", location=Point(0, 0), speed_kmh=30, reliability_score=0.95
    )
    defaults.update(overrides)
    return Driver(**defaults)


class TestRiskEngineAssess:
    def test_healthy_order_has_low_risk(self):
        engine = RiskEngine()
        order = make_order(status=OrderStatus.CREATED)
        assessment = engine.assess(
            order,
            merchant=make_merchant(),
            customer=make_customer(),
            driver=None,
            now=NOW,
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id=None,
        )
        assert 0 <= assessment.overall_risk_score <= 100
        assert assessment.overall_risk_score < 30
        assert assessment.predicted_failure_type is None

    def test_long_unassigned_wait_raises_no_driver_risk(self):
        engine = RiskEngine()
        order = make_order(status=OrderStatus.CONFIRMED)
        assessment = engine.assess(
            order,
            merchant=make_merchant(),
            customer=make_customer(),
            driver=None,
            now=NOW + timedelta(minutes=14),
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=14.0,
            max_wait_for_driver_minutes=15.0,
            delivery_id=None,
        )
        names = {f.name for f in assessment.factors}
        assert "driver_unassigned_wait" in names
        wait_factor = next(f for f in assessment.factors if f.name == "driver_unassigned_wait")
        assert wait_factor.raw_signal > 0.9

    def test_unreliable_driver_after_pickup_predicts_driver_never_arrived(self):
        engine = RiskEngine(risk_threshold_for_prediction=0.0)
        order = make_order(status=OrderStatus.EN_ROUTE_TO_CUSTOMER)
        assessment = engine.assess(
            order,
            merchant=make_merchant(),
            customer=make_customer(reachability_score=1.0),
            driver=make_driver(reliability_score=0.1, location=Point(4, 0)),
            now=NOW + timedelta(minutes=20),
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id="delivery-1",
        )
        assert assessment.predicted_failure_type == PredictedFailureType.DRIVER_NEVER_ARRIVED

    def test_perishable_overdue_contributes_only_when_applicable(self):
        engine = RiskEngine()
        order = make_order(
            status=OrderStatus.EN_ROUTE_TO_CUSTOMER,
            is_perishable=True,
            promised_delivery_time=NOW + timedelta(minutes=5),
        )
        assessment = engine.assess(
            order,
            merchant=make_merchant(),
            customer=make_customer(),
            driver=make_driver(location=Point(4, 0)),
            now=NOW + timedelta(minutes=20),  # already past promised time
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id="delivery-1",
        )
        factor = next(f for f in assessment.factors if f.name == "perishable_overdue")
        assert factor.raw_signal == 1.0

        non_perishable_order = make_order(
            status=OrderStatus.EN_ROUTE_TO_CUSTOMER,
            is_perishable=False,
            promised_delivery_time=NOW + timedelta(minutes=5),
        )
        assessment_2 = engine.assess(
            non_perishable_order,
            merchant=make_merchant(),
            customer=make_customer(),
            driver=make_driver(location=Point(4, 0)),
            now=NOW + timedelta(minutes=20),
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id="delivery-1",
        )
        assert "perishable_overdue" not in {f.name for f in assessment_2.factors}

    def test_terminal_order_has_zero_risk_and_full_confidence(self):
        engine = RiskEngine()
        order = make_order(status=OrderStatus.CONFIRMED)
        order.transition_to(OrderStatus.ASSIGNED, at=NOW)
        order.transition_to(
            OrderStatus.CANCELLED,
            at=NOW,
            cancellation_reason=CancellationReason.NO_DRIVER_AVAILABLE,
        )
        assessment = engine.assess(
            order,
            merchant=make_merchant(),
            customer=make_customer(),
            driver=None,
            now=NOW,
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id=None,
        )
        assert assessment.overall_risk_score == 0.0
        assert assessment.confidence == 1.0
        assert assessment.factors == []

    def test_factor_weights_sum_normalization_keeps_score_in_bounds(self):
        engine = RiskEngine()
        order = make_order(status=OrderStatus.EN_ROUTE_TO_CUSTOMER, is_perishable=True)
        assessment = engine.assess(
            order,
            merchant=make_merchant(reliability_score=0.0),
            customer=make_customer(reachability_score=0.0),
            driver=make_driver(reliability_score=0.0, location=Point(10, 10)),
            now=NOW + timedelta(hours=5),
            is_rush_hour=True,
            travel_speed_multiplier=0.3,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id="delivery-1",
        )
        assert 0 <= assessment.overall_risk_score <= 100

    @pytest.mark.parametrize("distance_scale", [0.1, 100.0])
    def test_score_always_bounded_regardless_of_distance(self, distance_scale):
        engine = RiskEngine()
        order = make_order(status=OrderStatus.EN_ROUTE_TO_MERCHANT)
        assessment = engine.assess(
            order,
            merchant=make_merchant(),
            customer=make_customer(location=Point(distance_scale, 0)),
            driver=make_driver(location=Point(distance_scale, distance_scale)),
            now=NOW,
            is_rush_hour=False,
            travel_speed_multiplier=1.0,
            avg_driver_speed_kmh=30,
            waited_for_driver_minutes=None,
            max_wait_for_driver_minutes=15,
            delivery_id="delivery-1",
        )
        assert 0 <= assessment.overall_risk_score <= 100


class TestRiskAssessmentServiceIntegration:
    def _run_with_risk_service(self, **config_overrides):
        defaults = dict(
            seed=42,
            start_time=NOW,
            duration_minutes=400,
            num_merchants=15,
            num_drivers=20,
            num_customers=300,
            base_order_rate_per_minute=1.0,
            map_size_km=12.0,
        )
        defaults.update(config_overrides)
        config = SimulationConfig(**defaults)
        bus = InProcessEventBus()
        engine = SimulationEngine(config, event_bus=bus)
        service = RiskAssessmentService(
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
        run = engine.run()
        return run, service

    def test_every_order_gets_at_least_one_assessment(self):
        run, service = self._run_with_risk_service()
        assert set(service.latest_assessment) == set(run.orders)
        assert len(service.history) == len(run.orders)

    def test_risk_rises_before_a_late_delivery_and_settles_to_zero_after(self):
        run, service = self._run_with_risk_service()
        late_delivered_orders = [
            o
            for o in run.orders.values()
            if o.status == OrderStatus.DELIVERED and o.is_late(as_of=o.delivered_at)
        ]
        assert len(late_delivered_orders) > 0
        order = late_delivered_orders[0]
        history = service.history[order.id]
        pre_terminal_scores = [a.overall_risk_score for a in history[:-1]]
        assert max(pre_terminal_scores) > 0
        assert history[-1].overall_risk_score == 0.0  # terminal snapshot

    def test_all_scores_bounded_across_a_full_run(self):
        run, service = self._run_with_risk_service(base_order_rate_per_minute=2.0, num_drivers=5)
        for assessments in service.history.values():
            for a in assessments:
                assert 0 <= a.overall_risk_score <= 100
                assert 0 <= a.confidence <= 1
