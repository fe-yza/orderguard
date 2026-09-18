"""Event-reactive wiring for the intervention engine.

Subscribes to the same event bus as `RiskAssessmentService` and, for every
event, looks up the risk assessment that service *just* computed for that
order (event bus subscribers run synchronously in registration order — see
`events/bus.py` — so as long as this service is constructed after the risk
service, the assessment is always fresh) and selects an intervention for it.
"""

from __future__ import annotations

from collections.abc import Callable

from orderguard.domain.events import DeliveryEvent
from orderguard.domain.order import Order
from orderguard.events.bus import EventBus
from orderguard.interventions.engine import InterventionEngine
from orderguard.interventions.models import InterventionDecision, InterventionType
from orderguard.risk.engine import RiskAssessmentService


class InterventionService:
    """`on_decision`, when given, is called once per *newly applied*
    intervention (the first time a given `InterventionType` is chosen for an
    order — repeated re-selection of the same type across reassessments
    isn't charged or re-applied again, since a real system wouldn't re-send
    the same notification or re-dispatch the same driver swap every time risk
    is recomputed). This is the hook the experiment framework (Milestone 5)
    uses to feed effects back into the simulation via
    `SimulationEngine.apply_intervention_effect`.
    """

    def __init__(
        self,
        intervention_engine: InterventionEngine,
        risk_service: RiskAssessmentService,
        event_bus: EventBus,
        *,
        orders: dict[str, Order],
        deliveries: dict,
        on_decision: Callable[[InterventionDecision], None] | None = None,
    ) -> None:
        self.intervention_engine = intervention_engine
        self._risk_service = risk_service
        self._orders = orders
        self._deliveries = deliveries
        self._on_decision = on_decision
        self.latest_decision: dict[str, InterventionDecision] = {}
        self.history: dict[str, list[InterventionDecision]] = {}
        self.applied_types: dict[str, set[InterventionType]] = {}
        self.total_applied_cost: dict[str, float] = {}
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

        if decision.chosen == InterventionType.DO_NOTHING:
            return
        already_applied = self.applied_types.setdefault(order.id, set())
        if decision.chosen in already_applied:
            return
        already_applied.add(decision.chosen)
        self.total_applied_cost[order.id] = (
            self.total_applied_cost.get(order.id, 0.0) + decision.chosen_candidate.direct_cost
        )
        if self._on_decision is not None:
            self._on_decision(decision)
