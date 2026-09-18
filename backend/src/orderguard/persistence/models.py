"""SQLAlchemy ORM models.

Mirrors the domain model in `domain/` but is a separate set of classes, not
a reuse of the dataclasses there — the domain layer stays free of any
persistence-framework dependency (see `docs/architecture.md`). Conversion
between the two lives in `persistence/repository.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from orderguard.domain.enums import (
    CancellationReason,
    EventType,
    FailureReason,
    OrderStatus,
)
from orderguard.interventions.models import InterventionType
from orderguard.risk.models import PredictedFailureType


class Base(DeclarativeBase):
    pass


def _str_enum(enum_cls: type, name: str) -> SAEnum:
    """All our domain enums are `StrEnum`s whose `.value` (lowercase) is
    what the rest of the codebase serializes/compares against (JSON
    payloads, API filters). SQLAlchemy's `Enum` defaults to using `.name`
    (upper-case) for storage, which would silently break any string-based
    filter — force `.value` instead so DB storage matches everywhere else.
    """
    return SAEnum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class SimulationRunRecord(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(primary_key=True)
    seed: Mapped[int]
    config: Mapped[dict] = mapped_column(JSONB)
    started_at: Mapped[datetime]
    completed_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC).replace(tzinfo=None)
    )

    merchants: Mapped[list[MerchantRecord]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan"
    )
    drivers: Mapped[list[DriverRecord]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan"
    )
    customers: Mapped[list[CustomerRecord]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan"
    )
    orders: Mapped[list[OrderRecord]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan"
    )
    metrics: Mapped[list[SimulationMetricsRecord]] = relationship(
        back_populates="simulation_run", cascade="all, delete-orphan"
    )


class MerchantRecord(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    name: Mapped[str]
    location_x_km: Mapped[float]
    location_y_km: Mapped[float]
    base_prep_minutes: Mapped[float]
    prep_time_stddev_minutes: Mapped[float]
    rush_hour_multiplier: Mapped[float]
    reliability_score: Mapped[float]
    final_backlog: Mapped[int]

    simulation_run: Mapped[SimulationRunRecord] = relationship(back_populates="merchants")


class DriverRecord(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    name: Mapped[str]
    location_x_km: Mapped[float]
    location_y_km: Mapped[float]
    speed_kmh: Mapped[float]
    reliability_score: Mapped[float]
    final_status: Mapped[str]

    simulation_run: Mapped[SimulationRunRecord] = relationship(back_populates="drivers")


class CustomerRecord(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    name: Mapped[str]
    location_x_km: Mapped[float]
    location_y_km: Mapped[float]
    reachability_score: Mapped[float]

    simulation_run: Mapped[SimulationRunRecord] = relationship(back_populates="customers")


class OrderRecord(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    created_at: Mapped[datetime]
    promised_delivery_time: Mapped[datetime]
    item_count: Mapped[int]
    is_perishable: Mapped[bool]
    status: Mapped[OrderStatus] = mapped_column(_str_enum(OrderStatus, "order_status"))
    delivered_at: Mapped[datetime | None]
    cancellation_reason: Mapped[CancellationReason | None] = mapped_column(
        _str_enum(CancellationReason, "cancellation_reason")
    )
    failure_reason: Mapped[FailureReason | None] = mapped_column(
        _str_enum(FailureReason, "failure_reason")
    )

    simulation_run: Mapped[SimulationRunRecord] = relationship(back_populates="orders")
    delivery: Mapped[DeliveryRecord | None] = relationship(
        back_populates="order", cascade="all, delete-orphan", uselist=False
    )
    events: Mapped[list[DeliveryEventRecord]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="DeliveryEventRecord.occurred_at",
    )
    risk_assessments: Mapped[list[RiskAssessmentRecord]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="RiskAssessmentRecord.computed_at",
    )
    intervention_decisions: Mapped[list[InterventionDecisionRecord]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="InterventionDecisionRecord.computed_at",
    )


class DeliveryRecord(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    merchant_id: Mapped[str]
    customer_id: Mapped[str]
    assigned_at: Mapped[datetime]

    order: Mapped[OrderRecord] = relationship(back_populates="delivery")


class DeliveryEventRecord(Base):
    __tablename__ = "delivery_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    delivery_id: Mapped[str | None]
    event_type: Mapped[EventType] = mapped_column(_str_enum(EventType, "event_type"))
    occurred_at: Mapped[datetime]
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    order: Mapped[OrderRecord] = relationship(back_populates="events")


class RiskAssessmentRecord(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    delivery_id: Mapped[str | None]
    computed_at: Mapped[datetime]
    overall_risk_score: Mapped[float]
    predicted_failure_type: Mapped[PredictedFailureType | None] = mapped_column(
        _str_enum(PredictedFailureType, "predicted_failure_type")
    )
    confidence: Mapped[float]
    predicted_delay_minutes: Mapped[float]
    factors: Mapped[list] = mapped_column(JSONB, default=list)

    order: Mapped[OrderRecord] = relationship(back_populates="risk_assessments")


class InterventionDecisionRecord(Base):
    __tablename__ = "intervention_decisions"

    id: Mapped[str] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    delivery_id: Mapped[str | None]
    risk_assessment_id: Mapped[str] = mapped_column(ForeignKey("risk_assessments.id"))
    computed_at: Mapped[datetime]
    chosen: Mapped[InterventionType] = mapped_column(
        _str_enum(InterventionType, "intervention_type")
    )
    rationale: Mapped[str]
    candidates: Mapped[list] = mapped_column(JSONB, default=list)

    order: Mapped[OrderRecord] = relationship(back_populates="intervention_decisions")


class SimulationMetricsRecord(Base):
    __tablename__ = "simulation_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[str] = mapped_column(ForeignKey("simulation_runs.id"))
    strategy: Mapped[str]
    total_orders: Mapped[int]
    delivered_count: Mapped[int]
    failed_count: Mapped[int]
    cancelled_count: Mapped[int]
    in_flight_count: Mapped[int]
    late_delivered_count: Mapped[int]
    late_rate: Mapped[float]
    failure_rate: Mapped[float]
    cancellation_rate: Mapped[float]
    avg_delay_minutes: Mapped[float]
    p50_delay_minutes: Mapped[float]
    p95_delay_minutes: Mapped[float]
    intervention_count: Mapped[int]
    intervention_rate: Mapped[float]
    total_intervention_cost: Mapped[float]
    failure_reason_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    cancellation_reason_counts: Mapped[dict] = mapped_column(JSONB, default=dict)

    simulation_run: Mapped[SimulationRunRecord] = relationship(back_populates="metrics")
