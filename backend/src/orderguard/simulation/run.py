"""Output of a completed (or in-progress) simulation.

Lives in `simulation/`, not `domain/`, because it composes a
`SimulationConfig` — a simulation-layer concept. `domain/` stays dependency-free
per `docs/architecture.md`. The persistence layer (Milestone 6) maps this
onto the `SimulationRun` / `SimulationMetrics` database tables; this class is
the in-memory equivalent, produced directly by the engine with no DB
involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from orderguard.domain.customer import Customer
from orderguard.domain.delivery import Delivery
from orderguard.domain.driver import Driver
from orderguard.domain.events import DeliveryEvent
from orderguard.domain.merchant import Merchant
from orderguard.domain.order import Order
from orderguard.simulation.config import SimulationConfig


@dataclass(slots=True)
class SimulationRun:
    id: str
    config: SimulationConfig
    started_at: datetime
    completed_at: datetime
    merchants: dict[str, Merchant]
    drivers: dict[str, Driver]
    customers: dict[str, Customer]
    orders: dict[str, Order]
    deliveries: dict[str, Delivery]
    events: list[DeliveryEvent]
