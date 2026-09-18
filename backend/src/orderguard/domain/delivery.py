"""Delivery entity.

Created once a driver is assigned to an order (see `docs/architecture.md` —
an order can fail/cancel before a delivery ever exists). Carries the
timestamped timeline (`DeliveryEvent`s) used both for the persisted history
and, from Milestone 2 onward, as the payload published on the event bus.

Deliberately has no `status` field of its own — `Order.status` is the single
source of truth for lifecycle state; duplicating it here would let the two
drift out of sync.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from orderguard.domain.events import DeliveryEvent


@dataclass(slots=True)
class Delivery:
    id: str
    order_id: str
    driver_id: str
    merchant_id: str
    customer_id: str
    assigned_at: datetime
    timeline: list[DeliveryEvent] = field(default_factory=list)

    def record(self, event: DeliveryEvent) -> None:
        self.timeline.append(event)
