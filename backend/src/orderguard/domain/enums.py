"""Enumerations for the OrderGuard domain model.

Kept as plain `StrEnum` (not `IntEnum`) so values serialize cleanly to JSON at
the API boundary later, and so log lines / DB rows are human-readable without
a lookup table.
"""

from enum import StrEnum, auto


class OrderStatus(StrEnum):
    """Canonical order lifecycle. Single source of truth for where an order
    is — `Delivery` does not carry a duplicate status field.

    Lateness is *not* a status: a late order that eventually completes is
    still `DELIVERED` (see `Order.is_late`). `FAILED` is reserved for orders
    that never complete as expected.
    """

    CREATED = auto()
    CONFIRMED = auto()
    ASSIGNED = auto()
    EN_ROUTE_TO_MERCHANT = auto()
    ARRIVED_AT_MERCHANT = auto()
    PICKED_UP = auto()
    EN_ROUTE_TO_CUSTOMER = auto()
    DELIVERED = auto()
    FAILED = auto()
    CANCELLED = auto()


# Terminal states — once here, an order/delivery no longer advances.
TERMINAL_ORDER_STATUSES = frozenset(
    {OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.CANCELLED}
)

# Valid forward transitions. Enforced by `Order.transition_to`; anything not
# listed here (including skipping a step) is a bug, not a valid outcome.
ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset({OrderStatus.ASSIGNED, OrderStatus.CANCELLED}),
    OrderStatus.ASSIGNED: frozenset(
        {OrderStatus.EN_ROUTE_TO_MERCHANT, OrderStatus.CANCELLED, OrderStatus.FAILED}
    ),
    OrderStatus.EN_ROUTE_TO_MERCHANT: frozenset(
        {OrderStatus.ARRIVED_AT_MERCHANT, OrderStatus.FAILED}
    ),
    OrderStatus.ARRIVED_AT_MERCHANT: frozenset({OrderStatus.PICKED_UP, OrderStatus.FAILED}),
    OrderStatus.PICKED_UP: frozenset({OrderStatus.EN_ROUTE_TO_CUSTOMER, OrderStatus.FAILED}),
    OrderStatus.EN_ROUTE_TO_CUSTOMER: frozenset({OrderStatus.DELIVERED, OrderStatus.FAILED}),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.FAILED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


class DriverStatus(StrEnum):
    """`offline` is reachable from any non-offline state (shift end, app
    closed, connectivity loss) — modeled separately rather than in
    `DRIVER_TRANSITIONS` since it's an interrupt, not a normal step.
    """

    AVAILABLE = auto()
    EN_ROUTE = auto()
    WAITING = auto()
    DELIVERING = auto()
    OFFLINE = auto()


class CancellationReason(StrEnum):
    """Why an order was deliberately stopped, as opposed to failing.

    Distinct from `FailureReason`: a cancellation is a decision (merchant is
    out of stock, no driver ever picked it up); a failure is the delivery
    attempt itself going wrong after it was underway.
    """

    MERCHANT_OUT_OF_STOCK = auto()
    NO_DRIVER_AVAILABLE = auto()
    CUSTOMER_CHANGED_MIND = auto()


class FailureReason(StrEnum):
    """Why a delivery in progress ended in `OrderStatus.FAILED`."""

    DRIVER_NEVER_ARRIVED = auto()
    NEVER_PICKED_UP = auto()
    DAMAGED_OR_SPOILED = auto()
    CUSTOMER_UNREACHABLE = auto()


class EventType(StrEnum):
    """Discrete, observable moments recorded on a delivery's timeline. This
    is the vocabulary both the persisted `DeliveryEvent` log and the
    Milestone 2 event bus payloads use.
    """

    ORDER_CREATED = auto()
    ORDER_CONFIRMED = auto()
    ORDER_CANCELLED = auto()
    DRIVER_ASSIGNED = auto()
    DRIVER_EN_ROUTE_TO_MERCHANT = auto()
    DRIVER_ARRIVED_AT_MERCHANT = auto()
    ORDER_PICKED_UP = auto()
    DRIVER_EN_ROUTE_TO_CUSTOMER = auto()
    ORDER_DELIVERED = auto()
    ORDER_FAILED = auto()
    DRIVER_WENT_OFFLINE = auto()
