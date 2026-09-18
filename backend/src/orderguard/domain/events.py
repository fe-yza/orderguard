"""`DeliveryEvent` — a single recorded, timestamped moment on a delivery's
timeline.

This is the same vocabulary the Milestone 2 event bus will publish: the
simulation engine appends one of these to `Delivery.timeline` on every state
change, and (starting Milestone 2) also publishes it to subscribers instead
of subscribers polling entity state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from orderguard.domain.enums import EventType


@dataclass(frozen=True, slots=True)
class DeliveryEvent:
    delivery_id: str
    order_id: str
    event_type: EventType
    occurred_at: datetime
    details: dict[str, Any] = field(default_factory=dict)
    """Small, event-specific payload (e.g. {"driver_id": ..., "reason": ...}).
    Kept as a plain dict rather than a subclass per event type — the set of
    fields is small and this avoids a combinatorial explosion of dataclasses
    for what's fundamentally a log line."""
