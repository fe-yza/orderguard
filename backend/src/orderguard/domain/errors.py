"""Domain-level exceptions."""

from __future__ import annotations

from orderguard.domain.enums import OrderStatus


class InvalidTransitionError(ValueError):
    """Raised when code attempts a state transition not present in
    `ORDER_TRANSITIONS`. This is always a bug in the caller (simulation
    engine or a test), never an expected runtime condition — it is not
    caught anywhere, by design.
    """

    def __init__(self, entity: str, from_status: OrderStatus, to_status: OrderStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"{entity}: cannot transition from {from_status} to {to_status}")
