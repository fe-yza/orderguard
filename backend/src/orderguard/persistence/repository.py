"""Translates between in-memory domain/simulation objects and DB records.

Nothing above the persistence layer should import SQLAlchemy directly (see
`docs/architecture.md`) — this module is the only place that does.
"""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from orderguard.experiments.models import SimulationMetrics
from orderguard.interventions.models import InterventionDecision
from orderguard.persistence.models import (
    CustomerRecord,
    DeliveryEventRecord,
    DeliveryRecord,
    DriverRecord,
    InterventionDecisionRecord,
    MerchantRecord,
    OrderRecord,
    RiskAssessmentRecord,
    SimulationMetricsRecord,
    SimulationRunRecord,
)
from orderguard.risk.models import RiskAssessment
from orderguard.simulation.run import SimulationRun


def save_simulation_run(
    session: Session,
    run: SimulationRun,
    *,
    risk_history: dict[str, list[RiskAssessment]] | None = None,
    intervention_history: dict[str, list[InterventionDecision]] | None = None,
) -> SimulationRunRecord:
    risk_history = risk_history or {}
    intervention_history = intervention_history or {}

    config_dict = asdict(run.config)
    config_dict["start_time"] = run.config.start_time.isoformat()

    run_record = SimulationRunRecord(
        id=run.id,
        seed=run.config.seed,
        config=config_dict,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )
    session.add(run_record)

    for merchant in run.merchants.values():
        session.add(
            MerchantRecord(
                id=merchant.id,
                simulation_run_id=run.id,
                name=merchant.name,
                location_x_km=merchant.location.x_km,
                location_y_km=merchant.location.y_km,
                base_prep_minutes=merchant.base_prep_minutes,
                prep_time_stddev_minutes=merchant.prep_time_stddev_minutes,
                rush_hour_multiplier=merchant.rush_hour_multiplier,
                reliability_score=merchant.reliability_score,
                final_backlog=merchant.active_order_backlog,
            )
        )

    for driver in run.drivers.values():
        session.add(
            DriverRecord(
                id=driver.id,
                simulation_run_id=run.id,
                name=driver.name,
                location_x_km=driver.location.x_km,
                location_y_km=driver.location.y_km,
                speed_kmh=driver.speed_kmh,
                reliability_score=driver.reliability_score,
                final_status=driver.status.value,
            )
        )

    for customer in run.customers.values():
        session.add(
            CustomerRecord(
                id=customer.id,
                simulation_run_id=run.id,
                name=customer.name,
                location_x_km=customer.location.x_km,
                location_y_km=customer.location.y_km,
                reachability_score=customer.reachability_score,
            )
        )

    for order in run.orders.values():
        session.add(
            OrderRecord(
                id=order.id,
                simulation_run_id=run.id,
                merchant_id=order.merchant_id,
                customer_id=order.customer_id,
                created_at=order.created_at,
                promised_delivery_time=order.promised_delivery_time,
                item_count=order.item_count,
                is_perishable=order.is_perishable,
                status=order.status,
                delivered_at=order.delivered_at,
                cancellation_reason=order.cancellation_reason,
                failure_reason=order.failure_reason,
            )
        )

    for delivery in run.deliveries.values():
        session.add(
            DeliveryRecord(
                id=delivery.id,
                order_id=delivery.order_id,
                driver_id=delivery.driver_id,
                merchant_id=delivery.merchant_id,
                customer_id=delivery.customer_id,
                assigned_at=delivery.assigned_at,
            )
        )

    for event in run.events:
        session.add(
            DeliveryEventRecord(
                order_id=event.order_id,
                delivery_id=event.delivery_id or None,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                details=event.details,
            )
        )

    for assessments in risk_history.values():
        for assessment in assessments:
            session.add(
                RiskAssessmentRecord(
                    id=assessment.id,
                    order_id=assessment.order_id,
                    delivery_id=assessment.delivery_id,
                    computed_at=assessment.computed_at,
                    overall_risk_score=assessment.overall_risk_score,
                    predicted_failure_type=assessment.predicted_failure_type,
                    confidence=assessment.confidence,
                    predicted_delay_minutes=assessment.predicted_delay_minutes,
                    factors=[asdict(f) for f in assessment.factors],
                )
            )

    # Flush before adding intervention_decisions rows: SQLAlchemy's automatic
    # insert-ordering across unrelated mapped classes (no `relationship()`
    # configured between RiskAssessmentRecord and InterventionDecisionRecord)
    # isn't reliable enough in practice to trust for a cross-table FK — an
    # explicit two-phase flush guarantees risk_assessments rows exist before
    # intervention_decisions rows referencing them are inserted.
    session.flush()

    for decisions in intervention_history.values():
        for decision in decisions:
            session.add(
                InterventionDecisionRecord(
                    id=decision.id,
                    order_id=decision.order_id,
                    delivery_id=decision.delivery_id,
                    risk_assessment_id=decision.risk_assessment_id,
                    computed_at=decision.computed_at,
                    chosen=decision.chosen,
                    rationale=decision.rationale,
                    candidates=[
                        {**asdict(c), "intervention_type": c.intervention_type.value}
                        for c in decision.candidates
                    ],
                )
            )

    session.commit()
    return run_record


def save_metrics(
    session: Session, simulation_run_id: str, metrics: SimulationMetrics
) -> SimulationMetricsRecord:
    record = SimulationMetricsRecord(
        simulation_run_id=simulation_run_id,
        strategy=metrics.strategy.value,
        total_orders=metrics.total_orders,
        delivered_count=metrics.delivered_count,
        failed_count=metrics.failed_count,
        cancelled_count=metrics.cancelled_count,
        in_flight_count=metrics.in_flight_count,
        late_delivered_count=metrics.late_delivered_count,
        late_rate=metrics.late_rate,
        failure_rate=metrics.failure_rate,
        cancellation_rate=metrics.cancellation_rate,
        avg_delay_minutes=metrics.avg_delay_minutes,
        p50_delay_minutes=metrics.p50_delay_minutes,
        p95_delay_minutes=metrics.p95_delay_minutes,
        intervention_count=metrics.intervention_count,
        intervention_rate=metrics.intervention_rate,
        total_intervention_cost=metrics.total_intervention_cost,
        failure_reason_counts=metrics.failure_reason_counts,
        cancellation_reason_counts=metrics.cancellation_reason_counts,
    )
    session.add(record)
    session.commit()
    return record


def list_simulation_runs(session: Session, *, limit: int = 50) -> list[SimulationRunRecord]:
    stmt = select(SimulationRunRecord).order_by(SimulationRunRecord.created_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


def get_simulation_run(session: Session, run_id: str) -> SimulationRunRecord | None:
    return session.get(SimulationRunRecord, run_id)


def list_orders_for_run(
    session: Session, run_id: str, *, status: str | None = None, limit: int = 100, offset: int = 0
) -> list[OrderRecord]:
    stmt = select(OrderRecord).where(OrderRecord.simulation_run_id == run_id)
    if status is not None:
        stmt = stmt.where(OrderRecord.status == status)
    stmt = stmt.order_by(OrderRecord.created_at).limit(limit).offset(offset)
    return list(session.execute(stmt).scalars())


def get_order_detail(session: Session, order_id: str) -> OrderRecord | None:
    stmt = (
        select(OrderRecord)
        .where(OrderRecord.id == order_id)
        .options(
            selectinload(OrderRecord.events),
            selectinload(OrderRecord.risk_assessments),
            selectinload(OrderRecord.intervention_decisions),
            selectinload(OrderRecord.delivery),
        )
    )
    return session.execute(stmt).scalar_one_or_none()


def get_latest_risk_assessments_for_run(
    session: Session, run_id: str, *, min_score: float = 0.0
) -> list[tuple[OrderRecord, RiskAssessmentRecord]]:
    """One (order, latest-risk-assessment) pair per order in the run, above
    `min_score`. Grouped in Python rather than a window-function query —
    simplest correct implementation for the order-of-magnitude of orders per
    run this project targets; revisit with a `ROW_NUMBER()` query if a
    benchmark (Milestone 8) shows this is actually a bottleneck."""
    stmt = (
        select(OrderRecord)
        .where(OrderRecord.simulation_run_id == run_id)
        .options(selectinload(OrderRecord.risk_assessments))
    )
    results = []
    for order in session.execute(stmt).scalars():
        if not order.risk_assessments:
            continue
        latest = max(order.risk_assessments, key=lambda a: a.computed_at)
        if latest.overall_risk_score >= min_score:
            results.append((order, latest))
    results.sort(key=lambda pair: pair[1].overall_risk_score, reverse=True)
    return results


def get_metrics_for_run(session: Session, run_id: str) -> list[SimulationMetricsRecord]:
    stmt = select(SimulationMetricsRecord).where(
        SimulationMetricsRecord.simulation_run_id == run_id
    )
    return list(session.execute(stmt).scalars())
