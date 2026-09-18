from collections import Counter
from datetime import datetime

import pytest

from orderguard.events.bus import InProcessEventBus
from orderguard.interventions.engine import InterventionEngine
from orderguard.interventions.models import InterventionType
from orderguard.interventions.service import InterventionService
from orderguard.risk.engine import RiskAssessmentService, RiskEngine
from orderguard.risk.models import PredictedFailureType, RiskAssessment
from orderguard.simulation.config import SimulationConfig
from orderguard.simulation.engine import SimulationEngine

NOW = datetime(2026, 1, 1, 12, 0, 0)


def make_assessment(
    *, overall_risk_score: float, predicted_failure_type: PredictedFailureType | None
) -> RiskAssessment:
    return RiskAssessment(
        id="risk-1",
        order_id="order-1",
        delivery_id=None,
        computed_at=NOW,
        overall_risk_score=overall_risk_score,
        predicted_failure_type=predicted_failure_type,
        confidence=0.8,
        predicted_delay_minutes=5.0,
        factors=[],
    )


class TestInterventionEngineSelect:
    def test_no_material_risk_selects_do_nothing_only(self):
        engine = InterventionEngine()
        assessment = make_assessment(overall_risk_score=5.0, predicted_failure_type=None)
        decision = engine.select(
            assessment, order_id="order-1", delivery_id=None, driver_assigned=False
        )
        assert decision.chosen == InterventionType.DO_NOTHING
        assert {c.intervention_type for c in decision.candidates} == {InterventionType.DO_NOTHING}

    def test_late_delivery_risk_considers_update_eta_and_notify_customer(self):
        engine = InterventionEngine()
        assessment = make_assessment(
            overall_risk_score=60.0, predicted_failure_type=PredictedFailureType.LATE_DELIVERY
        )
        decision = engine.select(
            assessment, order_id="order-1", delivery_id="delivery-1", driver_assigned=True
        )
        types = {c.intervention_type for c in decision.candidates}
        assert InterventionType.UPDATE_ETA in types
        assert InterventionType.NOTIFY_CUSTOMER in types
        assert InterventionType.DO_NOTHING in types
        assert InterventionType.REASSIGN_DRIVER not in types

    def test_reassign_driver_requires_driver_assigned(self):
        engine = InterventionEngine()
        assessment = make_assessment(
            overall_risk_score=60.0,
            predicted_failure_type=PredictedFailureType.DRIVER_NEVER_ARRIVED,
        )
        without_driver = engine.select(
            assessment, order_id="order-1", delivery_id=None, driver_assigned=False
        )
        with_driver = engine.select(
            assessment, order_id="order-1", delivery_id="delivery-1", driver_assigned=True
        )
        assert InterventionType.REASSIGN_DRIVER not in {
            c.intervention_type for c in without_driver.candidates
        }
        assert InterventionType.REASSIGN_DRIVER in {
            c.intervention_type for c in with_driver.candidates
        }

    def test_merchant_escalation_gated_by_min_risk_score(self):
        engine = InterventionEngine()
        low = make_assessment(
            overall_risk_score=30.0, predicted_failure_type=PredictedFailureType.NEVER_PICKED_UP
        )
        high = make_assessment(
            overall_risk_score=70.0, predicted_failure_type=PredictedFailureType.NEVER_PICKED_UP
        )
        low_decision = engine.select(
            low, order_id="order-1", delivery_id=None, driver_assigned=False
        )
        high_decision = engine.select(
            high, order_id="order-1", delivery_id=None, driver_assigned=False
        )
        assert InterventionType.MERCHANT_ESCALATION not in {
            c.intervention_type for c in low_decision.candidates
        }
        assert InterventionType.MERCHANT_ESCALATION in {
            c.intervention_type for c in high_decision.candidates
        }

    def test_expected_value_math_is_correct(self):
        engine = InterventionEngine()
        assessment = make_assessment(
            overall_risk_score=80.0,
            predicted_failure_type=PredictedFailureType.DRIVER_NEVER_ARRIVED,
        )
        decision = engine.select(
            assessment, order_id="order-1", delivery_id="delivery-1", driver_assigned=True
        )
        reassign = next(
            c
            for c in decision.candidates
            if c.intervention_type == InterventionType.REASSIGN_DRIVER
        )
        # failure_probability = 0.8, failure_cost = 18.0 (DRIVER_NEVER_ARRIVED),
        # probability_reduction = 0.6 -> residual_probability = 0.32
        expected_residual = 0.8 * (1 - 0.6) * 18.0
        assert reassign.residual_expected_failure_cost == pytest.approx(expected_residual)
        assert reassign.total_expected_cost == pytest.approx(2.00 + expected_residual)

    def test_chosen_never_worse_than_do_nothing(self):
        engine = InterventionEngine()
        for score in [10, 30, 45, 60, 80, 95]:
            for failure_type in PredictedFailureType:
                assessment = make_assessment(
                    overall_risk_score=score, predicted_failure_type=failure_type
                )
                decision = engine.select(
                    assessment, order_id="order-1", delivery_id="delivery-1", driver_assigned=True
                )
                assert decision.expected_savings_vs_do_nothing >= -1e-9

    def test_candidates_sorted_ascending_by_total_cost(self):
        engine = InterventionEngine()
        assessment = make_assessment(
            overall_risk_score=70.0, predicted_failure_type=PredictedFailureType.NEVER_PICKED_UP
        )
        decision = engine.select(
            assessment, order_id="order-1", delivery_id=None, driver_assigned=False
        )
        costs = [c.total_expected_cost for c in decision.candidates]
        assert costs == sorted(costs)
        assert decision.chosen == decision.candidates[0].intervention_type


class TestInterventionServiceIntegration:
    def test_full_run_produces_varied_decisions(self):
        config = SimulationConfig(
            seed=42,
            start_time=NOW,
            duration_minutes=400,
            num_merchants=15,
            num_drivers=20,
            num_customers=300,
            base_order_rate_per_minute=1.0,
            map_size_km=12.0,
        )
        bus = InProcessEventBus()
        engine = SimulationEngine(config, event_bus=bus)
        risk_service = RiskAssessmentService(
            RiskEngine(),
            bus,
            orders=engine.orders,
            merchants=engine.merchants,
            drivers=engine.drivers,
            customers=engine.customers,
            deliveries=engine.deliveries,
            config=config,
            clock=engine.clock,
        )
        intervention_service = InterventionService(
            InterventionEngine(),
            risk_service,
            bus,
            orders=engine.orders,
            deliveries=engine.deliveries,
        )
        run = engine.run()

        assert len(intervention_service.latest_decision) == len(run.orders)
        chosen_types = Counter(
            d.chosen for d in intervention_service.latest_decision.values()
        )
        # DO_NOTHING should dominate (most orders are healthy most of the time)
        assert chosen_types[InterventionType.DO_NOTHING] > 0
        # And at least one *other* lever should have fired somewhere across the run.
        ever_intervened = {
            d.chosen
            for decisions in intervention_service.history.values()
            for d in decisions
            if d.chosen != InterventionType.DO_NOTHING
        }
        assert len(ever_intervened) > 0
        for decisions in intervention_service.history.values():
            for d in decisions:
                assert d.expected_savings_vs_do_nothing >= -1e-9
