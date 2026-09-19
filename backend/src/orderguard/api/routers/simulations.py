"""Thin FastAPI routes — all business logic lives in `experiments/`,
`persistence/`. Routes only validate input, call into those modules, and
shape the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from orderguard.api.schemas import (
    CustomerOut,
    DriverOut,
    ExperimentRequest,
    ExperimentResponseOut,
    HighRiskOrderOut,
    MapEntitiesOut,
    MerchantOut,
    OrderDetailOut,
    OrderSummaryOut,
    RiskAssessmentOut,
    SimulationMetricsOut,
    SimulationRunSummaryOut,
)
from orderguard.experiments.runner import run_experiment_with_detail
from orderguard.persistence import repository
from orderguard.persistence.database import get_session

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", response_model=ExperimentResponseOut)
def create_experiment(
    request: ExperimentRequest, session: Session = Depends(get_session)
) -> ExperimentResponseOut:
    """Runs all three strategies (no-intervention / threshold / expected-value)
    on identical seeded conditions, persists the expected-value run's full
    detail plus every strategy's aggregate metrics, and returns the
    comparison. This is what the Simulation Lab page (Milestone 7) calls."""
    config = request.config.to_domain()
    result, run, risk_service, intervention_service = run_experiment_with_detail(
        config, threshold=request.threshold
    )
    repository.save_simulation_run(
        session,
        run,
        risk_history=risk_service.history,
        intervention_history=intervention_service.history,
    )
    for metrics in result.metrics_by_strategy.values():
        repository.save_metrics(session, run.id, metrics)

    return ExperimentResponseOut(
        simulation_run_id=run.id,
        threshold_used=result.threshold_used,
        metrics=[
            SimulationMetricsOut.model_validate(m, from_attributes=True)
            for m in result.metrics_by_strategy.values()
        ],
    )


@router.get("", response_model=list[SimulationRunSummaryOut])
def list_simulations(
    limit: int = 50, session: Session = Depends(get_session)
) -> list[SimulationRunSummaryOut]:
    runs = repository.list_simulation_runs(session, limit=limit)
    return [SimulationRunSummaryOut.model_validate(r) for r in runs]


@router.get("/{run_id}", response_model=SimulationRunSummaryOut)
def get_simulation(run_id: str, session: Session = Depends(get_session)) -> SimulationRunSummaryOut:
    run = repository.get_simulation_run(session, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return SimulationRunSummaryOut.model_validate(run)


@router.get("/{run_id}/metrics", response_model=list[SimulationMetricsOut])
def get_simulation_metrics(
    run_id: str, session: Session = Depends(get_session)
) -> list[SimulationMetricsOut]:
    if repository.get_simulation_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    metrics = repository.get_metrics_for_run(session, run_id)
    return [SimulationMetricsOut.model_validate(m) for m in metrics]


@router.get("/{run_id}/orders", response_model=list[OrderSummaryOut])
def list_simulation_orders(
    run_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> list[OrderSummaryOut]:
    if repository.get_simulation_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    orders = repository.list_orders_for_run(
        session, run_id, status=status, limit=limit, offset=offset
    )
    return [OrderSummaryOut.model_validate(o) for o in orders]


@router.get("/{run_id}/map", response_model=MapEntitiesOut)
def get_map_entities(run_id: str, session: Session = Depends(get_session)) -> MapEntitiesOut:
    if repository.get_simulation_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return MapEntitiesOut(
        merchants=[
            MerchantOut.model_validate(m) for m in repository.get_merchants_for_run(session, run_id)
        ],
        drivers=[
            DriverOut.model_validate(d) for d in repository.get_drivers_for_run(session, run_id)
        ],
        customers=[
            CustomerOut.model_validate(c)
            for c in repository.get_customers_for_run(session, run_id)
        ],
    )


@router.get("/{run_id}/orders/{order_id}", response_model=OrderDetailOut)
def get_order(
    run_id: str, order_id: str, session: Session = Depends(get_session)
) -> OrderDetailOut:
    """The Order Inspector's data source: timeline, risk factor history, and
    every intervention decision (with its full cost-comparison candidates)
    ever made for this order. Scoped by run_id — order IDs like
    "order-000042" are only unique within a single run (see
    `persistence/models.py`), so there is no unscoped lookup."""
    order = repository.get_order_detail(session, run_id, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetailOut.model_validate(order)


@router.get("/{run_id}/high-risk", response_model=list[HighRiskOrderOut])
def get_high_risk_orders(
    run_id: str, min_score: float = 50.0, session: Session = Depends(get_session)
) -> list[HighRiskOrderOut]:
    if repository.get_simulation_run(session, run_id) is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    pairs = repository.get_latest_risk_assessments_for_run(session, run_id, min_score=min_score)
    return [
        HighRiskOrderOut(
            order=OrderSummaryOut.model_validate(order),
            latest_risk_assessment=RiskAssessmentOut.model_validate(assessment),
        )
        for order, assessment in pairs
    ]
