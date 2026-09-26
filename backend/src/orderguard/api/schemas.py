"""Pydantic request/response schemas — the API boundary. Untrusted input
(request bodies) is validated here before ever touching the simulation
dataclasses, per `docs/architecture.md`'s boundary decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orderguard.domain.enums import TERMINAL_ORDER_STATUSES
from orderguard.simulation.config import RushHourWindow, SimulationConfig

TERMINAL_STATUS_VALUES = frozenset(s.value for s in TERMINAL_ORDER_STATUSES)


class RushHourWindowIn(BaseModel):
    start_minute: int = Field(ge=0)
    end_minute: int
    # demand_multiplier scales order spawn rate directly (see
    # simulation/engine.py's _spawn_orders), so it's bounded for the same
    # reason base_order_rate_per_minute is below -- an unbounded multiplier
    # would let a small base rate still produce an unbounded order count.
    demand_multiplier: float = Field(gt=0, le=5)
    speed_multiplier: float = Field(gt=0, le=1)

    def to_domain(self) -> RushHourWindow:
        return RushHourWindow(
            start_minute=self.start_minute,
            end_minute=self.end_minute,
            demand_multiplier=self.demand_multiplier,
            speed_multiplier=self.speed_multiplier,
        )


class SimulationConfigIn(BaseModel):
    """Request-side simulation config. Every size/rate field carries an
    upper bound in addition to Pydantic's usual `gt`/`ge` lower bound: this
    is public, unauthenticated input (see `api/rate_limit.py`), and the
    engine's cost scales with duration_minutes x order-spawn-rate x
    entity-count, so an unbounded field here would let one request run
    arbitrarily long. Bounds are set well above every real value used by
    the demo/tour/UI (documented per-field) so nothing legitimate is
    affected -- see `docs/deployment.md`-equivalent note in the README.
    """

    seed: int
    start_time: datetime
    duration_minutes: int = Field(gt=0, le=1440)  # UI/tour max used: 480
    num_merchants: int = Field(gt=0, le=100)  # UI/tour max used: 20
    num_drivers: int = Field(gt=0, le=300)  # UI/tour max used: 35
    num_customers: int = Field(gt=0, le=2000)  # UI/tour max used: 300
    base_order_rate_per_minute: float = Field(gt=0, le=5)  # UI/tour max used: 1.4
    map_size_km: float = Field(gt=0, le=500)  # UI/tour max used: 14.0
    avg_driver_speed_kmh: float = Field(default=30.0, gt=0, le=200)
    driver_speed_stddev_kmh: float = Field(default=5.0, ge=0, le=100)
    avg_merchant_prep_minutes: float = Field(default=12.0, gt=0, le=180)
    merchant_prep_stddev_minutes: float = Field(default=3.0, ge=0, le=90)
    promised_delivery_buffer_minutes: float = Field(default=25.0, gt=0, le=360)
    tick_minutes: int = Field(default=1, ge=1, le=60)
    max_wait_for_driver_minutes: float = Field(default=15.0, gt=0, le=360)
    driver_offline_probability_per_tick: float = Field(default=0.0008, ge=0, le=1)
    merchant_stockout_probability: float = Field(default=0.03, ge=0, le=1)
    customer_unreachable_probability: float = Field(default=0.02, ge=0, le=1)
    perishable_spoilage_probability_per_tick: float = Field(default=0.05, ge=0, le=1)
    rush_hour_windows: list[RushHourWindowIn] = Field(default_factory=list, max_length=20)

    def to_domain(self) -> SimulationConfig:
        return SimulationConfig(
            seed=self.seed,
            start_time=self.start_time,
            duration_minutes=self.duration_minutes,
            num_merchants=self.num_merchants,
            num_drivers=self.num_drivers,
            num_customers=self.num_customers,
            base_order_rate_per_minute=self.base_order_rate_per_minute,
            map_size_km=self.map_size_km,
            avg_driver_speed_kmh=self.avg_driver_speed_kmh,
            driver_speed_stddev_kmh=self.driver_speed_stddev_kmh,
            avg_merchant_prep_minutes=self.avg_merchant_prep_minutes,
            merchant_prep_stddev_minutes=self.merchant_prep_stddev_minutes,
            promised_delivery_buffer_minutes=self.promised_delivery_buffer_minutes,
            tick_minutes=self.tick_minutes,
            max_wait_for_driver_minutes=self.max_wait_for_driver_minutes,
            driver_offline_probability_per_tick=self.driver_offline_probability_per_tick,
            merchant_stockout_probability=self.merchant_stockout_probability,
            customer_unreachable_probability=self.customer_unreachable_probability,
            perishable_spoilage_probability_per_tick=self.perishable_spoilage_probability_per_tick,
            rush_hour_windows=tuple(w.to_domain() for w in self.rush_hour_windows),
        )


class ExperimentRequest(BaseModel):
    config: SimulationConfigIn
    threshold: float = 50.0


class OrderSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    merchant_id: str
    customer_id: str
    status: str
    is_perishable: bool
    created_at: datetime
    promised_delivery_time: datetime
    delivered_at: datetime | None
    cancellation_reason: str | None
    failure_reason: str | None


class DeliveryEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    occurred_at: datetime
    details: dict[str, Any]


class RiskAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    computed_at: datetime
    overall_risk_score: float
    predicted_failure_type: str | None
    confidence: float
    predicted_delay_minutes: float
    factors: list[dict[str, Any]]


class InterventionDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    computed_at: datetime
    chosen: str
    rationale: str
    candidates: list[dict[str, Any]]


class OrderDetailOut(OrderSummaryOut):
    events: list[DeliveryEventOut]
    risk_assessments: list[RiskAssessmentOut]
    intervention_decisions: list[InterventionDecisionOut]


class HighRiskOrderOut(BaseModel):
    order: OrderSummaryOut
    latest_risk_assessment: RiskAssessmentOut


class MerchantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location_x_km: float
    location_y_km: float
    reliability_score: float
    final_backlog: int


class DriverOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location_x_km: float
    location_y_km: float
    reliability_score: float
    final_status: str


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location_x_km: float
    location_y_km: float
    reachability_score: float


class MapDeliveryOut(BaseModel):
    order_id: str
    status: str
    is_perishable: bool
    is_active: bool
    """True for orders not yet in a terminal state (delivered/failed/
    cancelled) as of the moment the run ended."""
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
    """The order's most recently computed risk score. Present for every
    order that reached CONFIRMED (i.e. almost all of them) — absent only if
    somehow no risk assessment was ever computed. This is a *measured*
    value read back from a stored assessment, not recomputed on the fly."""
    predicted_failure_type: str | None


class MapEntitiesOut(BaseModel):
    merchants: list[MerchantOut]
    drivers: list[DriverOut]
    customers: list[CustomerOut]
    deliveries: list[MapDeliveryOut]


class SimulationRunSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    seed: int
    started_at: datetime
    completed_at: datetime
    created_at: datetime


class SimulationMetricsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    strategy: str
    total_orders: int
    delivered_count: int
    failed_count: int
    cancelled_count: int
    in_flight_count: int
    late_delivered_count: int
    late_rate: float
    failure_rate: float
    cancellation_rate: float
    avg_delay_minutes: float
    p50_delay_minutes: float
    p95_delay_minutes: float
    intervention_count: int
    intervention_rate: float
    total_intervention_cost: float
    failure_reason_counts: dict[str, int]
    cancellation_reason_counts: dict[str, int]


class ExperimentResponseOut(BaseModel):
    simulation_run_id: str
    threshold_used: float
    metrics: list[SimulationMetricsOut]
