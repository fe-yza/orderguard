"""Thin FastAPI routes — all business logic lives in `experiments/`,
`persistence/`. Routes only validate input, call into those modules, and
shape the response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from orderguard.api.schemas import (
    ExperimentRequest,
    ExperimentResponseOut,
    HighRiskOrderOut,
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
