"""Pydantic request/response schemas — the API boundary. Untrusted input
(request bodies) is validated here before ever touching the simulation
dataclasses, per `docs/architecture.md`'s boundary decision.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orderguard.simulation.config import RushHourWindow, SimulationConfig


class RushHourWindowIn(BaseModel):
    start_minute: int = Field(ge=0)
    end_minute: int
    demand_multiplier: float = Field(gt=0)
    speed_multiplier: float = Field(gt=0, le=1)

    def to_domain(self) -> RushHourWindow:
        return RushHourWindow(
            start_minute=self.start_minute,
            end_minute=self.end_minute,
            demand_multiplier=self.demand_multiplier,
            speed_multiplier=self.speed_multiplier,
        )


class SimulationConfigIn(BaseModel):
    seed: int
    start_time: datetime
    duration_minutes: int = Field(gt=0)
    num_merchants: int = Field(gt=0)
    num_drivers: int = Field(gt=0)
    num_customers: int = Field(gt=0)
    base_order_rate_per_minute: float = Field(gt=0)
    map_size_km: float = Field(gt=0)
    avg_driver_speed_kmh: float = 30.0
    driver_speed_stddev_kmh: float = 5.0
    avg_merchant_prep_minutes: float = 12.0
    merchant_prep_stddev_minutes: float = 3.0
    promised_delivery_buffer_minutes: float = 25.0
    tick_minutes: int = 1
    max_wait_for_driver_minutes: float = 15.0
    driver_offline_probability_per_tick: float = Field(default=0.0008, ge=0, le=1)
    merchant_stockout_probability: float = Field(default=0.03, ge=0, le=1)
    customer_unreachable_probability: float = Field(default=0.02, ge=0, le=1)
    perishable_spoilage_probability_per_tick: float = Field(default=0.05, ge=0, le=1)
    rush_hour_windows: list[RushHourWindowIn] = Field(default_factory=list)

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


class MapEntitiesOut(BaseModel):
    merchants: list[MerchantOut]
    drivers: list[DriverOut]
    customers: list[CustomerOut]


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
