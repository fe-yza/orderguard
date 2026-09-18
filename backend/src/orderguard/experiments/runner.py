"""Runs the same seeded scenario under all three strategies and collects
comparable metrics.

"Identical seeded conditions" means identical *starting* conditions and
identical exogenous randomness draws up to the point an intervention
actually changes an outcome — not frozen outcomes. Once a strategy prevents
a hazard that another strategy doesn't, the two runs' RNG consumption
diverges (a prevented failure means that order keeps consuming random draws
in later ticks instead of being removed from the active pool), which is
exactly the counterfactual divergence the comparison is supposed to surface.
All three runs start from a fresh `SimulationEngine(config)` — the RNG is
re-seeded from `config.seed` each time — so the divergence is caused only by
each strategy's own decisions, not by leftover state between runs.
"""

from __future__ import annotations

import statistics
from collections import Counter

from orderguard.domain.enums import OrderStatus
from orderguard.events.bus import InProcessEventBus
from orderguard.experiments.models import ExperimentResult, SimulationMetrics, StrategyName
from orderguard.experiments.policies import ThresholdInterventionPolicy
from orderguard.interventions.engine import InterventionEngine
from orderguard.interventions.service import InterventionService
from orderguard.risk.engine import RiskAssessmentService, RiskEngine
from orderguard.simulation.config import SimulationConfig
from orderguard.simulation.engine import SimulationEngine
from orderguard.simulation.run import SimulationRun


def _run_no_intervention(config: SimulationConfig) -> tuple[SimulationRun, dict[str, float]]:
    engine = SimulationEngine(config)
    run = engine.run()
    return run, {}


def _run_threshold_based(
    config: SimulationConfig, threshold: float
) -> tuple[SimulationRun, dict[str, float]]:
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
    policy = ThresholdInterventionPolicy(
        risk_service,
        bus,
        orders=engine.orders,
        threshold=threshold,
        on_apply=engine.apply_intervention_effect,
    )
    run = engine.run()
    return run, policy.total_applied_cost


def run_expected_value_detailed(
    config: SimulationConfig,
) -> tuple[SimulationRun, RiskAssessmentService, InterventionService]:
    """Like the other `_run_*` helpers but returns the live services too —
    used when a caller (the API layer, when persisting an experiment) needs
    the full risk/intervention history, not just the aggregate metrics.
    """
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
        on_decision=lambda decision: engine.apply_intervention_effect(
            decision.order_id, decision.chosen_candidate.probability_reduction
        ),
    )
    run = engine.run()
    return run, risk_service, intervention_service


def _run_expected_value(config: SimulationConfig) -> tuple[SimulationRun, dict[str, float]]:
    run, _risk_service, intervention_service = run_expected_value_detailed(config)
    return run, intervention_service.total_applied_cost


def compute_metrics(
    run: SimulationRun, strategy: StrategyName, applied_cost_by_order: dict[str, float]
) -> SimulationMetrics:
    orders = list(run.orders.values())
    total_orders = len(orders)
    delivered = [o for o in orders if o.status == OrderStatus.DELIVERED]
    failed = [o for o in orders if o.status == OrderStatus.FAILED]
    cancelled = [o for o in orders if o.status == OrderStatus.CANCELLED]
    in_flight = [o for o in orders if not o.is_terminal]

    delays = [
        (o.delivered_at - o.promised_delivery_time).total_seconds() / 60 for o in delivered
    ]
    late_count = sum(1 for d in delays if d > 0)

    intervention_count = len(applied_cost_by_order)
    total_cost = sum(applied_cost_by_order.values())

    return SimulationMetrics(
        strategy=strategy,
        seed=run.config.seed,
        total_orders=total_orders,
        delivered_count=len(delivered),
        failed_count=len(failed),
        cancelled_count=len(cancelled),
        in_flight_count=len(in_flight),
        late_delivered_count=late_count,
        late_rate=(late_count / len(delivered)) if delivered else 0.0,
        failure_rate=(len(failed) / total_orders) if total_orders else 0.0,
        cancellation_rate=(len(cancelled) / total_orders) if total_orders else 0.0,
        avg_delay_minutes=statistics.fmean(delays) if delays else 0.0,
        p50_delay_minutes=_percentile(delays, 50),
        p95_delay_minutes=_percentile(delays, 95),
        intervention_count=intervention_count,
        intervention_rate=(intervention_count / total_orders) if total_orders else 0.0,
        total_intervention_cost=total_cost,
        failure_reason_counts=dict(Counter(o.failure_reason.value for o in failed)),
        cancellation_reason_counts=dict(
            Counter(o.cancellation_reason.value for o in cancelled)
        ),
    )


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    lower, upper = int(k), min(int(k) + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def run_experiment(config: SimulationConfig, *, threshold: float = 50.0) -> ExperimentResult:
    no_intervention_run, no_intervention_cost = _run_no_intervention(config)
    threshold_run, threshold_cost = _run_threshold_based(config, threshold)
    expected_value_run, expected_value_cost = _run_expected_value(config)

    metrics_by_strategy = {
        StrategyName.NO_INTERVENTION: compute_metrics(
            no_intervention_run, StrategyName.NO_INTERVENTION, no_intervention_cost
        ),
        StrategyName.THRESHOLD_BASED: compute_metrics(
            threshold_run, StrategyName.THRESHOLD_BASED, threshold_cost
        ),
        StrategyName.EXPECTED_VALUE: compute_metrics(
            expected_value_run, StrategyName.EXPECTED_VALUE, expected_value_cost
        ),
    }
    return ExperimentResult(
        seed=config.seed, threshold_used=threshold, metrics_by_strategy=metrics_by_strategy
    )


def run_experiment_with_detail(
    config: SimulationConfig, *, threshold: float = 50.0
) -> tuple[ExperimentResult, SimulationRun, RiskAssessmentService, InterventionService]:
    """Same comparison as `run_experiment`, but also returns the
    expected-value strategy's full run + services (risk/intervention
    history) — the persistence layer needs these to save order-level detail,
    not just the aggregate metrics."""
    no_intervention_run, no_intervention_cost = _run_no_intervention(config)
    threshold_run, threshold_cost = _run_threshold_based(config, threshold)
    expected_value_run, risk_service, intervention_service = run_expected_value_detailed(config)

    metrics_by_strategy = {
        StrategyName.NO_INTERVENTION: compute_metrics(
            no_intervention_run, StrategyName.NO_INTERVENTION, no_intervention_cost
        ),
        StrategyName.THRESHOLD_BASED: compute_metrics(
            threshold_run, StrategyName.THRESHOLD_BASED, threshold_cost
        ),
        StrategyName.EXPECTED_VALUE: compute_metrics(
            expected_value_run,
            StrategyName.EXPECTED_VALUE,
            intervention_service.total_applied_cost,
        ),
    }
    result = ExperimentResult(
        seed=config.seed, threshold_used=threshold, metrics_by_strategy=metrics_by_strategy
    )
    return result, expected_value_run, risk_service, intervention_service
