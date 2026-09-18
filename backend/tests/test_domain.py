from datetime import datetime, timedelta

import pytest

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
from orderguard.domain.errors import InvalidTransitionError
from orderguard.domain.events import DeliveryEvent
from orderguard.domain.geo import Point
from orderguard.domain.merchant import Merchant
from orderguard.domain.order import Order

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
    )
    defaults.update(overrides)
    return Order(**defaults)


class TestMerchant:
    def test_valid_merchant(self):
        m = Merchant(
            id="m1",
            name="Test Merchant",
            location=Point(0, 0),
            base_prep_minutes=10,
            prep_time_stddev_minutes=2,
            rush_hour_multiplier=1.5,
            reliability_score=0.9,
        )
        assert m.expected_prep_minutes(is_rush_hour=False) == pytest.approx(10.0)
        assert m.expected_prep_minutes(is_rush_hour=True) == pytest.approx(15.0)

    def test_backlog_increases_expected_prep_time(self):
        m = Merchant(
            id="m1",
            name="Busy Merchant",
            location=Point(0, 0),
            base_prep_minutes=10,
            prep_time_stddev_minutes=2,
            rush_hour_multiplier=1.0,
            reliability_score=0.9,
            active_order_backlog=5,
        )
        assert m.expected_prep_minutes(is_rush_hour=False) == pytest.approx(10 * 1.4)

    @pytest.mark.parametrize(
        "field_name,value",
        [
            ("reliability_score", 1.5),
            ("reliability_score", -0.1),
            ("base_prep_minutes", 0),
            ("prep_time_stddev_minutes", -1),
            ("rush_hour_multiplier", 0),
        ],
    )
    def test_invalid_values_rejected(self, field_name, value):
        kwargs = dict(
            id="m1",
            name="X",
            location=Point(0, 0),
            base_prep_minutes=10,
            prep_time_stddev_minutes=2,
            rush_hour_multiplier=1.5,
            reliability_score=0.9,
        )
        kwargs[field_name] = value
        with pytest.raises(ValueError):
            Merchant(**kwargs)


class TestDriver:
    def test_move_toward_partial_step(self):
        d = Driver(id="d1", name="D", location=Point(0, 0), speed_kmh=30, reliability_score=0.9)
        arrived = d.move_toward(Point(10, 0), minutes=10, speed_multiplier=1.0)
        # 30 km/h for 10 minutes = 5 km, target is 10 km away.
        assert arrived is False
        assert d.location.x_km == pytest.approx(5.0)

    def test_move_toward_snaps_on_arrival(self):
        d = Driver(id="d1", name="D", location=Point(0, 0), speed_kmh=30, reliability_score=0.9)
        arrived = d.move_toward(Point(2, 0), minutes=10, speed_multiplier=1.0)
        assert arrived is True
        assert d.location == Point(2, 0)

    def test_speed_multiplier_slows_travel(self):
        d = Driver(id="d1", name="D", location=Point(0, 0), speed_kmh=30, reliability_score=0.9)
        d.move_toward(Point(10, 0), minutes=10, speed_multiplier=0.5)
        assert d.location.x_km == pytest.approx(2.5)

    def test_invalid_speed_rejected(self):
        with pytest.raises(ValueError):
            Driver(id="d1", name="D", location=Point(0, 0), speed_kmh=0, reliability_score=0.9)

    def test_is_available(self):
        d = Driver(id="d1", name="D", location=Point(0, 0), speed_kmh=30, reliability_score=0.9)
        assert d.is_available is True
        d.status = DriverStatus.DELIVERING
        assert d.is_available is False


class TestCustomer:
    def test_invalid_reachability_rejected(self):
        with pytest.raises(ValueError):
            Customer(id="c1", name="C", location=Point(0, 0), reachability_score=1.1)


class TestOrderLifecycle:
    def test_initial_state(self):
        order = make_order()
        assert order.status == OrderStatus.CREATED
        assert order.status_history == [(OrderStatus.CREATED, NOW)]
        assert order.is_terminal is False

    def test_happy_path_transitions(self):
        order = make_order()
        t = NOW
        for status in [
            OrderStatus.CONFIRMED,
            OrderStatus.ASSIGNED,
            OrderStatus.EN_ROUTE_TO_MERCHANT,
            OrderStatus.ARRIVED_AT_MERCHANT,
            OrderStatus.PICKED_UP,
            OrderStatus.EN_ROUTE_TO_CUSTOMER,
        ]:
            t += timedelta(minutes=5)
            order.transition_to(status, at=t)
            assert order.status == status

        t += timedelta(minutes=5)
        order.transition_to(OrderStatus.DELIVERED, at=t)
        assert order.status == OrderStatus.DELIVERED
        assert order.delivered_at == t
        assert order.is_terminal is True

    def test_invalid_transition_raises(self):
        order = make_order()
        with pytest.raises(InvalidTransitionError):
            order.transition_to(OrderStatus.DELIVERED, at=NOW)

    def test_cannot_leave_terminal_state(self):
        order = make_order()
        order.transition_to(
            OrderStatus.CANCELLED,
            at=NOW,
            cancellation_reason=CancellationReason.MERCHANT_OUT_OF_STOCK,
        )
        assert order.is_terminal is True
        with pytest.raises(InvalidTransitionError):
            order.transition_to(OrderStatus.CONFIRMED, at=NOW)

    def test_cancellation_requires_reason(self):
        order = make_order()
        with pytest.raises(ValueError):
            order.transition_to(OrderStatus.CANCELLED, at=NOW)

    def test_failure_requires_reason(self):
        order = make_order()
        order.transition_to(OrderStatus.CONFIRMED, at=NOW)
        order.transition_to(OrderStatus.ASSIGNED, at=NOW)
        with pytest.raises(ValueError):
            order.transition_to(OrderStatus.FAILED, at=NOW)

    def test_failure_records_reason(self):
        order = make_order()
        order.transition_to(OrderStatus.CONFIRMED, at=NOW)
        order.transition_to(OrderStatus.ASSIGNED, at=NOW)
        order.transition_to(
            OrderStatus.FAILED, at=NOW, failure_reason=FailureReason.DRIVER_NEVER_ARRIVED
        )
        assert order.failure_reason == FailureReason.DRIVER_NEVER_ARRIVED

    def test_is_late_before_delivery_uses_as_of(self):
        order = make_order()
        on_time_check = order.is_late(as_of=order.promised_delivery_time - timedelta(minutes=1))
        late_check = order.is_late(as_of=order.promised_delivery_time + timedelta(minutes=1))
        assert on_time_check is False
        assert late_check is True

    def test_is_late_after_delivery_uses_delivered_at(self):
        order = make_order()
        order.transition_to(OrderStatus.CONFIRMED, at=NOW)
        order.transition_to(OrderStatus.ASSIGNED, at=NOW)
        order.transition_to(OrderStatus.EN_ROUTE_TO_MERCHANT, at=NOW)
        order.transition_to(OrderStatus.ARRIVED_AT_MERCHANT, at=NOW)
        order.transition_to(OrderStatus.PICKED_UP, at=NOW)
        order.transition_to(OrderStatus.EN_ROUTE_TO_CUSTOMER, at=NOW)
        late_delivery_time = order.promised_delivery_time + timedelta(minutes=10)
        order.transition_to(OrderStatus.DELIVERED, at=late_delivery_time)
        # Even checking "as_of" way earlier, delivered_at governs once set.
        assert order.is_late(as_of=NOW) is True

    def test_rejects_promised_time_before_created(self):
        with pytest.raises(ValueError):
            make_order(promised_delivery_time=NOW - timedelta(minutes=1))

    def test_rejects_non_positive_item_count(self):
        with pytest.raises(ValueError):
            make_order(item_count=0)


class TestDelivery:
    def test_record_appends_to_timeline(self):
        delivery = Delivery(
            id="del-1",
            order_id="order-1",
            driver_id="driver-1",
            merchant_id="merchant-1",
            customer_id="customer-1",
            assigned_at=NOW,
        )
        event = DeliveryEvent(
            delivery_id="del-1",
            order_id="order-1",
            event_type=EventType.DRIVER_ASSIGNED,
            occurred_at=NOW,
        )
        delivery.record(event)
        assert delivery.timeline == [event]
