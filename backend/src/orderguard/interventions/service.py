"""Event-reactive wiring for the intervention engine.

Subscribes to the same event bus as `RiskAssessmentService` and, for every
event, looks up the risk assessment that service *just* computed for that
order (event bus subscribers run synchronously in registration order — see
`events/bus.py` — so as long as this service is constructed after the risk
service, the assessment is always fresh) and selects an intervention for it.
"""

from __future__ import annotations

from orderguard.domain.events import DeliveryEvent
from orderguard.domain.order import Order
from orderguard.events.bus import EventBus
from orderguard.interventions.engine import InterventionEngine
from orderguard.interventions.models import InterventionDecision
from orderguard.risk.engine import RiskAssessmentService


class InterventionService:
    def __init__(
        self,
        intervention_engine: InterventionEngine,
        risk_service: RiskAssessmentService,
        event_bus: EventBus,
        *,
        orders: dict[str, Order],
        deliveries: dict,
    ) -> None:
        self.intervention_engine = intervention_engine
        self._risk_service = risk_service
        self._orders = orders
        self._deliveries = deliveries
        self.latest_decision: dict[str, InterventionDecision] = {}
        self.history: dict[str, list[InterventionDecision]] = {}
        event_bus.subscribe(self._on_event)

    def _on_event(self, event: DeliveryEvent) -> None:
        order = self._orders.get(event.order_id)
        assessment = self._risk_service.latest_assessment.get(event.order_id)
        if order is None or assessment is None:
            return

        delivery = self._deliveries.get(order.id)
        decision = self.intervention_engine.select(
            assessment,
            order_id=order.id,
            delivery_id=delivery.id if delivery is not None else None,
            driver_assigned=delivery is not None,
        )
        self.latest_decision[order.id] = decision
        self.history.setdefault(order.id, []).append(decision)
