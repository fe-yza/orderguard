from datetime import datetime

from orderguard.domain.enums import EventType
from orderguard.domain.events import DeliveryEvent
from orderguard.events.bus import InProcessEventBus

NOW = datetime(2026, 1, 1, 8, 0, 0)


def make_event(event_type: EventType) -> DeliveryEvent:
    return DeliveryEvent(
        delivery_id="delivery-1", order_id="order-1", event_type=event_type, occurred_at=NOW
    )


class TestInProcessEventBus:
    def test_specific_subscriber_receives_matching_event(self):
        bus = InProcessEventBus()
        received = []
        bus.subscribe(received.append, event_type=EventType.ORDER_CREATED)

        bus.publish(make_event(EventType.ORDER_CREATED))
        bus.publish(make_event(EventType.ORDER_DELIVERED))

        assert len(received) == 1
        assert received[0].event_type == EventType.ORDER_CREATED

    def test_wildcard_subscriber_receives_every_event(self):
        bus = InProcessEventBus()
        received = []
        bus.subscribe(received.append)

        bus.publish(make_event(EventType.ORDER_CREATED))
        bus.publish(make_event(EventType.ORDER_DELIVERED))

        assert len(received) == 2

    def test_multiple_subscribers_all_receive_event(self):
        bus = InProcessEventBus()
        received_a, received_b = [], []
        bus.subscribe(received_a.append, event_type=EventType.ORDER_FAILED)
        bus.subscribe(received_b.append, event_type=EventType.ORDER_FAILED)

        bus.publish(make_event(EventType.ORDER_FAILED))

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_no_subscribers_does_not_raise(self):
        bus = InProcessEventBus()
        bus.publish(make_event(EventType.ORDER_CREATED))
