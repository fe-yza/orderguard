from datetime import datetime

from orderguard.events.bus import InProcessEventBus
from orderguard.experiments.models import StrategyName
from orderguard.experiments.runner import compute_metrics
from orderguard.interventions.engine import InterventionEngine
from orderguard.interventions.service import InterventionService
from orderguard.persistence import repository
from orderguard.risk.engine import RiskAssessmentService, RiskEngine
from orderguard.simulation.config import SimulationConfig
from orderguard.simulation.engine import SimulationEngine

NOW = datetime(2026, 1, 1, 8, 0, 0)


def _run_full_stack(seed: int = 1):
    config = SimulationConfig(
        seed=seed,
        start_time=NOW,
        duration_minutes=200,
        num_merchants=8,
        num_drivers=15,
        num_customers=100,
        base_order_rate_per_minute=0.8,
        map_size_km=8.0,
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
        on_decision=lambda d: engine.apply_intervention_effect(
            d.order_id, d.chosen_candidate.probability_reduction
        ),
    )
    run = engine.run()
    return run, risk_service, intervention_service


class TestPersistenceRoundTrip:
    def test_save_and_fetch_simulation_run(self, db_session):
        run, risk_service, intervention_service = _run_full_stack()
        repository.save_simulation_run(
            db_session,
            run,
            risk_history=risk_service.history,
            intervention_history=intervention_service.history,
        )

        fetched = repository.get_simulation_run(db_session, run.id)
        assert fetched is not None
        assert fetched.seed == run.config.seed
        assert len(fetched.orders) == len(run.orders)
        assert len(fetched.merchants) == len(run.merchants)
        assert len(fetched.drivers) == len(run.drivers)
        assert len(fetched.customers) == len(run.customers)

    def test_appears_in_list_simulation_runs(self, db_session):
        run, risk_service, intervention_service = _run_full_stack(seed=2)
        repository.save_simulation_run(
            db_session,
            run,
            risk_history=risk_service.history,
            intervention_history=intervention_service.history,
        )
        runs = repository.list_simulation_runs(db_session)
        assert any(r.id == run.id for r in runs)

    def test_list_orders_for_run_filters_by_status(self, db_session):
        run, risk_service, intervention_service = _run_full_stack(seed=3)
        repository.save_simulation_run(
            db_session,
            run,
            risk_history=risk_service.history,
            intervention_history=intervention_service.history,
        )
        delivered = repository.list_orders_for_run(
            db_session, run.id, status="delivered", limit=1000
        )
        assert len(delivered) > 0
        assert all(o.status == "delivered" for o in delivered)

    def test_order_detail_includes_events_risk_and_interventions(self, db_session):
        run, risk_service, intervention_service = _run_full_stack(seed=4)
        repository.save_simulation_run(
            db_session,
            run,
            risk_history=risk_service.history,
            intervention_history=intervention_service.history,
        )
        any_order_id = next(iter(run.orders))
        detail = repository.get_order_detail(db_session, any_order_id)
        assert detail is not None
        assert len(detail.events) > 0
        assert len(detail.risk_assessments) == len(risk_service.history[any_order_id])
        assert len(detail.intervention_decisions) == len(
            intervention_service.history[any_order_id]
        )

    def test_latest_risk_assessments_sorted_and_filtered(self, db_session):
        run, risk_service, intervention_service = _run_full_stack(seed=5)
        repository.save_simulation_run(
            db_session,
            run,
            risk_history=risk_service.history,
            intervention_history=intervention_service.history,
        )
        pairs = repository.get_latest_risk_assessments_for_run(db_session, run.id, min_score=0.0)
        assert len(pairs) == len(run.orders)
        scores = [assessment.overall_risk_score for _order, assessment in pairs]
        assert scores == sorted(scores, reverse=True)

        high_only = repository.get_latest_risk_assessments_for_run(
            db_session, run.id, min_score=99.0
        )
        assert all(a.overall_risk_score >= 99.0 for _order, a in high_only)

    def test_save_and_fetch_metrics(self, db_session):
        run, risk_service, intervention_service = _run_full_stack(seed=6)
        repository.save_simulation_run(
            db_session,
            run,
            risk_history=risk_service.history,
            intervention_history=intervention_service.history,
        )
        metrics = compute_metrics(
            run, StrategyName.EXPECTED_VALUE, intervention_service.total_applied_cost
        )
        repository.save_metrics(db_session, run.id, metrics)

        fetched = repository.get_metrics_for_run(db_session, run.id)
        assert len(fetched) == 1
        assert fetched[0].strategy == "expected_value"
        assert fetched[0].total_orders == metrics.total_orders
        assert fetched[0].late_rate == metrics.late_rate
