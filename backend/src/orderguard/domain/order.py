"""Order entity and its lifecycle state machine.

`Order` is the single source of truth for lifecycle status (see
`docs/architecture.md`); `Delivery` does not duplicate it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from orderguard.domain.enums import (
    ORDER_TRANSITIONS,
    TERMINAL_ORDER_STATUSES,
    CancellationReason,
    FailureReason,
    OrderStatus,
)
from orderguard.domain.errors import InvalidTransitionError


@dataclass(slots=True)
class Order:
    id: str
    merchant_id: str
    customer_id: str
    created_at: datetime
    promised_delivery_time: datetime
    item_count: int
    is_perishable: bool
    status: OrderStatus = OrderStatus.CREATED
    delivered_at: datetime | None = None
    cancellation_reason: CancellationReason | None = None
    failure_reason: FailureReason | None = None
    status_history: list[tuple[OrderStatus, datetime]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.item_count <= 0:
            raise ValueError(f"item_count must be > 0, got {self.item_count}")
        if self.promised_delivery_time <= self.created_at:
            raise ValueError("promised_delivery_time must be after created_at")
        self.status_history.append((self.status, self.created_at))

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_ORDER_STATUSES

    def is_late(self, *, as_of: datetime) -> bool:
        """Whether the order has missed its promised window as of `as_of`.

        Lateness is a derived comparison, not a status — a delivered order
        that ran past its promise is still `DELIVERED`, just late. Metrics
        (Milestone 5) compute the late rate by calling this rather than
        relying on a stored flag, so it stays consistent with whatever
        `promised_delivery_time` actually is.
        """
        reference = self.delivered_at if self.delivered_at is not None else as_of
        return reference > self.promised_delivery_time

    def transition_to(
        self,
        new_status: OrderStatus,
        *,
        at: datetime,
        cancellation_reason: CancellationReason | None = None,
        failure_reason: FailureReason | None = None,
    ) -> None:
        allowed = ORDER_TRANSITIONS.get(self.status, frozenset())
        if new_status not in allowed:
            raise InvalidTransitionError("Order", self.status, new_status)

        if new_status == OrderStatus.CANCELLED and cancellation_reason is None:
            raise ValueError("cancellation_reason is required when transitioning to CANCELLED")
        if new_status == OrderStatus.FAILED and failure_reason is None:
            raise ValueError("failure_reason is required when transitioning to FAILED")

        self.status = new_status
        self.status_history.append((new_status, at))
        if new_status == OrderStatus.DELIVERED:
            self.delivered_at = at
        elif new_status == OrderStatus.CANCELLED:
            self.cancellation_reason = cancellation_reason
        elif new_status == OrderStatus.FAILED:
            self.failure_reason = failure_reason
