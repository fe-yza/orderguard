"""The `THRESHOLD_BASED` baseline: a naive ops-team policy that fires the
same fixed action on every order once its risk score crosses a fixed bar,
regardless of predicted cause, cost, or whether the action even applies to
the order's current state. Contrasted against `InterventionEngine`'s
cost-aware, cause-specific selection in the Milestone 5 experiment
comparison — same underlying `RiskEngine` scores, different decision layer,
so the comparison isolates the effect of the *decision policy* rather than
also varying the risk model.
"""

from __future__ import annotations

from collections.abc import Callable

from orderguard.domain.events import DeliveryEvent
from orderguard.domain.order import Order
from orderguard.events.bus import EventBus
from orderguard.risk.engine import RiskAssessmentService


class ThresholdInterventionPolicy:
    def __init__(
        self,
        risk_service: RiskAssessmentService,
        event_bus: EventBus,
        *,
        orders: dict[str, Order],
        threshold: float,
        intervention_cost: float = 1.00,
        probability_reduction: float = 0.30,
        on_apply: Callable[[str, float], None] | None = None,
    ) -> None:
        self._risk_service = risk_service
        self._orders = orders
        self.threshold = threshold
        self.intervention_cost = intervention_cost
        self.probability_reduction = probability_reduction
        self._on_apply = on_apply
        self.applied_order_ids: set[str] = set()
        self.total_applied_cost: dict[str, float] = {}
        event_bus.subscribe(self._on_event)

    def _on_event(self, event: DeliveryEvent) -> None:
        if event.order_id in self.applied_order_ids:
            return
        order = self._orders.get(event.order_id)
        assessment = self._risk_service.latest_assessment.get(event.order_id)
        if order is None or assessment is None:
            return
        if assessment.overall_risk_score < self.threshold:
            return
        if assessment.predicted_failure_type is None:
            return

        self.applied_order_ids.add(order.id)
        self.total_applied_cost[order.id] = self.intervention_cost
        if self._on_apply is not None:
            self._on_apply(order.id, self.probability_reduction)
