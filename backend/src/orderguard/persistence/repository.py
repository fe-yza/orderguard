"""Translates between in-memory domain/simulation objects and DB records.

Nothing above the persistence layer should import SQLAlchemy directly (see
`docs/architecture.md`) — this module is the only place that does.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, aliased, selectinload

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
                simulation_run_id=run.id,
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
                simulation_run_id=run.id,
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
                    simulation_run_id=run.id,
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
                    simulation_run_id=run.id,
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


def get_order_detail(session: Session, run_id: str, order_id: str) -> OrderRecord | None:
    """`order_id` (e.g. "order-000042") is only unique *within* a run — see
    the module docstring on `persistence/models.py` — so this always takes
    `run_id` too, never a bare order lookup. There is no unscoped
    equivalent; callers that only have an order_id must also know which
    run it came from (the frontend always does, since it only ever gets an
    order_id from a run-scoped list/feed in the first place)."""
    stmt = (
        select(OrderRecord)
        .where(OrderRecord.simulation_run_id == run_id, OrderRecord.id == order_id)
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
    `min_score`.

    Originally grouped in Python (`selectinload` every order's *entire*
    risk-assessment history, then `max()` in a loop) as the simplest correct
    v1. Milestone 8 benchmarking measured this endpoint at ~1.8s on a 5K-order
    run — order of magnitude slower than every other endpoint (map: ~20ms,
    orders list: ~3ms) — because it was pulling every historical assessment
    for every order (risk is reassessed on every event; a 5K-order run had
    ~30K assessment rows) just to throw all but the newest away in Python.
    Replaced with a `ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY
    computed_at DESC)` window-function query that lets Postgres pick the
    latest row per order directly — confirmed via direct query timing this
    drops to ~0.16s server-side for the same run.
    """
    row_number = (
        func.row_number()
        .over(
            partition_by=RiskAssessmentRecord.order_id,
            order_by=RiskAssessmentRecord.computed_at.desc(),
        )
        .label("rn")
    )
    latest_subq = (
        select(RiskAssessmentRecord, row_number)
        .where(RiskAssessmentRecord.simulation_run_id == run_id)
        .subquery()
    )
    latest_assessment = aliased(RiskAssessmentRecord, latest_subq)

    stmt = (
        select(OrderRecord, latest_assessment)
        .join(latest_assessment, latest_assessment.order_id == OrderRecord.id)
        .where(
            OrderRecord.simulation_run_id == run_id,
            latest_subq.c.rn == 1,
            latest_subq.c.overall_risk_score >= min_score,
        )
        .order_by(latest_subq.c.overall_risk_score.desc())
    )
    return list(session.execute(stmt).all())


@dataclass(slots=True)
class DeliveryMapRow:
    """One order's map-relevant state: its fixed merchant/customer
    endpoints, its driver's *current* position if a delivery exists (this
    is exact for orders still in flight when the run ended — the driver
    genuinely hasn't moved since — and simply the driver's last position
    before moving on to something else for terminal orders), and its latest
    risk assessment if one was ever computed. Feeds the Overview map."""

    order_id: str
    status: str
    is_perishable: bool
    merchant_id: str
    merchant_x_km: float
    merchant_y_km: float
    customer_id: str
    customer_x_km: float
    customer_y_km: float
    driver_id: str | None
    driver_x_km: float | None
    driver_y_km: float | None
    driver_status: str | None
    latest_risk_score: float | None
    predicted_failure_type: str | None


def get_delivery_map_for_run(session: Session, run_id: str) -> list[DeliveryMapRow]:
    """Every order in the run with enough state to draw it on a map: its
    merchant/customer endpoints, its driver (if assigned), and its latest
    risk score (if any was ever computed). One query, not N+1 — every join
    condition includes `simulation_run_id` explicitly, because merchant/
    driver/customer/order IDs are only unique *within* a run (composite
    keys — see this module's docstring); a join on the bare id column alone
    would silently match the wrong run's row once more than one run
    exists.
    """
    row_number = (
        func.row_number()
        .over(
            partition_by=RiskAssessmentRecord.order_id,
            order_by=RiskAssessmentRecord.computed_at.desc(),
        )
        .label("rn")
    )
    latest_risk_subq = (
        select(
            RiskAssessmentRecord.order_id,
            RiskAssessmentRecord.overall_risk_score,
            RiskAssessmentRecord.predicted_failure_type,
            row_number,
        )
        .where(RiskAssessmentRecord.simulation_run_id == run_id)
        .subquery()
    )

    stmt = (
        select(
            OrderRecord.id,
            OrderRecord.status,
            OrderRecord.is_perishable,
            MerchantRecord.id,
            MerchantRecord.location_x_km,
            MerchantRecord.location_y_km,
            CustomerRecord.id,
            CustomerRecord.location_x_km,
            CustomerRecord.location_y_km,
            DriverRecord.id,
            DriverRecord.location_x_km,
            DriverRecord.location_y_km,
            DriverRecord.final_status,
            latest_risk_subq.c.overall_risk_score,
            latest_risk_subq.c.predicted_failure_type,
        )
        .join(
            MerchantRecord,
            and_(
                MerchantRecord.simulation_run_id == OrderRecord.simulation_run_id,
                MerchantRecord.id == OrderRecord.merchant_id,
            ),
        )
        .join(
            CustomerRecord,
            and_(
                CustomerRecord.simulation_run_id == OrderRecord.simulation_run_id,
                CustomerRecord.id == OrderRecord.customer_id,
            ),
        )
        .outerjoin(
            DeliveryRecord,
            and_(
                DeliveryRecord.simulation_run_id == OrderRecord.simulation_run_id,
                DeliveryRecord.order_id == OrderRecord.id,
            ),
        )
        .outerjoin(
            DriverRecord,
            and_(
                DriverRecord.simulation_run_id == OrderRecord.simulation_run_id,
                DriverRecord.id == DeliveryRecord.driver_id,
            ),
        )
        .outerjoin(
            latest_risk_subq,
            and_(
                latest_risk_subq.c.order_id == OrderRecord.id,
                latest_risk_subq.c.rn == 1,
            ),
        )
        .where(OrderRecord.simulation_run_id == run_id)
    )

    return [
        DeliveryMapRow(
            order_id=row[0],
            status=row[1],
            is_perishable=row[2],
            merchant_id=row[3],
            merchant_x_km=row[4],
            merchant_y_km=row[5],
            customer_id=row[6],
            customer_x_km=row[7],
            customer_y_km=row[8],
            driver_id=row[9],
            driver_x_km=row[10],
            driver_y_km=row[11],
            driver_status=row[12],
            latest_risk_score=row[13],
            predicted_failure_type=row[14],
        )
        for row in session.execute(stmt).all()
    ]


def get_merchants_for_run(session: Session, run_id: str) -> list[MerchantRecord]:
    stmt = select(MerchantRecord).where(MerchantRecord.simulation_run_id == run_id)
    return list(session.execute(stmt).scalars())


def get_drivers_for_run(session: Session, run_id: str) -> list[DriverRecord]:
    stmt = select(DriverRecord).where(DriverRecord.simulation_run_id == run_id)
    return list(session.execute(stmt).scalars())


def get_customers_for_run(session: Session, run_id: str) -> list[CustomerRecord]:
    stmt = select(CustomerRecord).where(CustomerRecord.simulation_run_id == run_id)
    return list(session.execute(stmt).scalars())


def get_metrics_for_run(session: Session, run_id: str) -> list[SimulationMetricsRecord]:
    stmt = select(SimulationMetricsRecord).where(
        SimulationMetricsRecord.simulation_run_id == run_id
    )
    return list(session.execute(stmt).scalars())
