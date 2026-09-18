"""In-process event bus.

`EventBus` is a `Protocol` so callers (the simulation engine) depend on an
interface, not an implementation — swapping in a Kafka/Redis-backed bus later
means writing a new class that satisfies this protocol, not touching engine
or risk-engine code. `InProcessEventBus` is the only implementation for now,
per `docs/architecture.md` (no message broker until benchmarks show the
in-process bus is actually a bottleneck).

Dispatch is synchronous: `publish` calls every matching subscriber
immediately, in registration order, on the caller's thread. This is what
lets the risk engine "react to events rather than poll" — its handler runs
as part of the same call stack that produced the event, with no queue or
async machinery needed for a single-process simulation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Protocol

from orderguard.domain.enums import EventType
from orderguard.domain.events import DeliveryEvent

EventHandler = Callable[[DeliveryEvent], None]


class EventBus(Protocol):
    def subscribe(self, handler: EventHandler, event_type: EventType | None = None) -> None:
        """Register `handler` to be called on every published event whose
        `event_type` matches, or every event if `event_type` is None."""
        ...

    def publish(self, event: DeliveryEvent) -> None: ...


class InProcessEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[EventType | None, list[EventHandler]] = defaultdict(list)

    def subscribe(self, handler: EventHandler, event_type: EventType | None = None) -> None:
        self._subscribers[event_type].append(handler)

    def publish(self, event: DeliveryEvent) -> None:
        for handler in self._subscribers.get(event.event_type, ()):
            handler(event)
        for handler in self._subscribers.get(None, ()):
            handler(event)
