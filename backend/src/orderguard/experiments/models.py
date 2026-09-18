"""Experiment framework output types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, auto


class StrategyName(StrEnum):
    NO_INTERVENTION = auto()
    """Baseline: simulation runs with no risk engine or intervention engine
    attached at all — pure ground truth."""
    THRESHOLD_BASED = auto()
    """Naive ops-team baseline: any order whose risk score crosses a fixed
    threshold gets the same fixed intervention, regardless of predicted
    cause or cost."""
    EXPECTED_VALUE = auto()
    """OrderGuard's actual approach: `interventions/engine.py`'s
    cost-vs-expected-failure-cost selection."""


@dataclass(slots=True)
class SimulationMetrics:
    strategy: StrategyName
    seed: int
    total_orders: int
    delivered_count: int
    failed_count: int
    cancelled_count: int
    in_flight_count: int
    """Orders still non-terminal when the run's duration elapsed."""
    late_delivered_count: int
    """Among delivered orders, how many missed their promised time."""
    late_rate: float
    """late_delivered_count / delivered_count. 0 if nothing was delivered."""
    failure_rate: float
    """failed_count / total_orders."""
    cancellation_rate: float
    """cancelled_count / total_orders."""
    avg_delay_minutes: float
    """Mean (delivered_at - promised_delivery_time) over delivered orders.
    Negative means early on average."""
    p50_delay_minutes: float
    p95_delay_minutes: float
    intervention_count: int
    """Number of distinct orders that received at least one non-DO_NOTHING
    intervention."""
    intervention_rate: float
    """intervention_count / total_orders."""
    total_intervention_cost: float
    """Sum of each order's first-application cost per intervention type —
    see `interventions/service.py`'s dedup logic."""
    failure_reason_counts: dict[str, int] = field(default_factory=dict)
    cancellation_reason_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class ExperimentResult:
    seed: int
    threshold_used: float
    metrics_by_strategy: dict[StrategyName, SimulationMetrics]
