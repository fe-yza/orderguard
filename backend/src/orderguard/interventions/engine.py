"""Intervention selection via an expected-value model.

For a delivery with a given risk assessment, every applicable intervention
(including the implicit `DO_NOTHING`) is scored as:

    total_expected_cost = direct_cost + residual_expected_failure_cost
    residual_expected_failure_cost = (
        failure_probability * (1 - probability_reduction)
        * failure_cost * (1 - cost_reduction_fraction)
    )

`failure_probability` is the risk assessment's `overall_risk_score / 100` —
treating the 0-100 score as an implied probability is a deliberate modeling
simplification (documented, not hidden): it isn't a calibrated probability,
but it's the only failure-likelihood signal this system produces, and using
it consistently is what keeps the comparison defensible. The intervention
with the lowest `total_expected_cost` is selected — including `DO_NOTHING`
itself, when no intervention's math beats it.

Each catalog entry's `probability_reduction` and `cost_reduction_fraction`
are estimates of *how well that lever addresses this specific problem* (e.g.
`REASSIGN_DRIVER` cuts failure probability because it removes the actual
unreliable driver; `NOTIFY_CUSTOMER` cuts failure *cost* because it manages
expectations without changing what actually happens). These are documented
assumptions, not measured constants — a real system would learn them from
outcome data; this project doesn't have that data, so they're kept as
explicit, configurable numbers instead of hidden magic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from orderguard.interventions.models import (
    InterventionCandidate,
    InterventionDecision,
    InterventionType,
)
from orderguard.risk.models import PredictedFailureType, RiskAssessment

FAILURE_COST_BY_TYPE: dict[PredictedFailureType, float] = {
    PredictedFailureType.LATE_DELIVERY: 5.0,
    PredictedFailureType.NEVER_PICKED_UP: 15.0,
    PredictedFailureType.DRIVER_NEVER_ARRIVED: 18.0,
    PredictedFailureType.DAMAGED_OR_SPOILED: 20.0,
    PredictedFailureType.CUSTOMER_UNREACHABLE: 12.0,
    PredictedFailureType.NO_DRIVER_AVAILABLE: 15.0,
}
_DEFAULT_FAILURE_COST = 10.0
"""Used only if `predicted_failure_type` is somehow missing from the table
above (defensive default, not expected to be exercised)."""


@dataclass(frozen=True, slots=True)
class InterventionDefinition:
    intervention_type: InterventionType
    direct_cost: float
    probability_reduction: float
    cost_reduction_fraction: float
    applicable_failure_types: frozenset[PredictedFailureType]
    """Empty frozenset means "applicable for any predicted failure type"."""
    min_risk_score: float = 0.0
    requires_driver_assigned: bool = False


CATALOG: list[InterventionDefinition] = [
    InterventionDefinition(
        intervention_type=InterventionType.DO_NOTHING,
        direct_cost=0.0,
        probability_reduction=0.0,
        cost_reduction_fraction=0.0,
        applicable_failure_types=frozenset(),
    ),
    InterventionDefinition(
        intervention_type=InterventionType.UPDATE_ETA,
        direct_cost=0.10,
        probability_reduction=0.0,
        cost_reduction_fraction=0.10,
        applicable_failure_types=frozenset({PredictedFailureType.LATE_DELIVERY}),
    ),
    InterventionDefinition(
        intervention_type=InterventionType.NOTIFY_CUSTOMER,
        direct_cost=0.15,
        probability_reduction=0.0,
        cost_reduction_fraction=0.15,
        applicable_failure_types=frozenset(),
    ),
    InterventionDefinition(
        intervention_type=InterventionType.NOTIFY_MERCHANT,
        direct_cost=0.20,
        probability_reduction=0.20,
        cost_reduction_fraction=0.0,
        applicable_failure_types=frozenset({PredictedFailureType.NEVER_PICKED_UP}),
    ),
    InterventionDefinition(
        intervention_type=InterventionType.MERCHANT_ESCALATION,
        direct_cost=1.50,
        probability_reduction=0.45,
        cost_reduction_fraction=0.0,
        applicable_failure_types=frozenset({PredictedFailureType.NEVER_PICKED_UP}),
        min_risk_score=50.0,
    ),
    InterventionDefinition(
        intervention_type=InterventionType.OFFER_CREDIT,
        direct_cost=3.00,
        probability_reduction=0.0,
        cost_reduction_fraction=0.35,
        applicable_failure_types=frozenset(
            {
                PredictedFailureType.LATE_DELIVERY,
                PredictedFailureType.CUSTOMER_UNREACHABLE,
                PredictedFailureType.DAMAGED_OR_SPOILED,
            }
        ),
        min_risk_score=40.0,
    ),
    InterventionDefinition(
        intervention_type=InterventionType.REASSIGN_DRIVER,
        direct_cost=2.00,
        probability_reduction=0.60,
        cost_reduction_fraction=0.0,
        applicable_failure_types=frozenset(
            {PredictedFailureType.DRIVER_NEVER_ARRIVED, PredictedFailureType.NEVER_PICKED_UP}
        ),
        min_risk_score=35.0,
        requires_driver_assigned=True,
    ),
]


class InterventionEngine:
    def __init__(self, catalog: list[InterventionDefinition] | None = None) -> None:
        self.catalog = CATALOG if catalog is None else catalog

    def select(
        self,
        risk_assessment: RiskAssessment,
        *,
        order_id: str,
        delivery_id: str | None,
        driver_assigned: bool,
    ) -> InterventionDecision:
        failure_probability = risk_assessment.overall_risk_score / 100
        failure_cost = FAILURE_COST_BY_TYPE.get(
            risk_assessment.predicted_failure_type, _DEFAULT_FAILURE_COST
        )

        candidates: list[InterventionCandidate] = []
        for definition in self.catalog:
            if not self._is_applicable(definition, risk_assessment, driver_assigned):
                continue
            residual_probability = failure_probability * (1 - definition.probability_reduction)
            residual_cost = failure_cost * (1 - definition.cost_reduction_fraction)
            residual_expected_failure_cost = residual_probability * residual_cost
            candidates.append(
                InterventionCandidate(
                    intervention_type=definition.intervention_type,
                    direct_cost=definition.direct_cost,
                    failure_probability=failure_probability,
                    failure_cost=failure_cost,
                    probability_reduction=definition.probability_reduction,
                    cost_reduction_fraction=definition.cost_reduction_fraction,
                    residual_expected_failure_cost=residual_expected_failure_cost,
                    total_expected_cost=definition.direct_cost + residual_expected_failure_cost,
                )
            )

        candidates.sort(key=lambda c: c.total_expected_cost)
        chosen = candidates[0]
        rationale = self._explain(risk_assessment, chosen, candidates)

        return InterventionDecision(
            id=f"intervention-{uuid.uuid4()}",
            order_id=order_id,
            delivery_id=delivery_id,
            risk_assessment_id=risk_assessment.id,
            computed_at=risk_assessment.computed_at,
            chosen=chosen.intervention_type,
            rationale=rationale,
            candidates=candidates,
        )

    def _is_applicable(
        self,
        definition: InterventionDefinition,
        risk_assessment: RiskAssessment,
        driver_assigned: bool,
    ) -> bool:
        if definition.intervention_type == InterventionType.DO_NOTHING:
            return True
        if risk_assessment.predicted_failure_type is None:
            return False
        if risk_assessment.overall_risk_score < definition.min_risk_score:
            return False
        if definition.requires_driver_assigned and not driver_assigned:
            return False
        if (
            definition.applicable_failure_types
            and risk_assessment.predicted_failure_type not in definition.applicable_failure_types
        ):
            return False
        return True

    def _explain(
        self,
        risk_assessment: RiskAssessment,
        chosen: InterventionCandidate,
        candidates: list[InterventionCandidate],
    ) -> str:
        do_nothing = next(
            (c for c in candidates if c.intervention_type == InterventionType.DO_NOTHING), None
        )
        baseline = do_nothing.total_expected_cost if do_nothing else 0.0
        savings = baseline - chosen.total_expected_cost
        predicted = (
            risk_assessment.predicted_failure_type.value
            if risk_assessment.predicted_failure_type
            else "no material risk"
        )
        return (
            f"Risk score {risk_assessment.overall_risk_score:.1f}/100, predicted outcome: "
            f"{predicted}. Doing nothing has expected cost ${baseline:.2f}; "
            f"{chosen.intervention_type.value} costs ${chosen.direct_cost:.2f} direct plus "
            f"${chosen.residual_expected_failure_cost:.2f} residual expected failure cost "
            f"(${chosen.total_expected_cost:.2f} total) — saving ${savings:.2f} vs. doing nothing."
        )
