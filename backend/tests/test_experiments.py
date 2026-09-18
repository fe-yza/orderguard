from datetime import datetime

from orderguard.experiments.models import StrategyName
from orderguard.experiments.runner import run_experiment
from orderguard.simulation.config import RushHourWindow, SimulationConfig

NOW = datetime(2026, 1, 1, 8, 0, 0)


def make_config(**overrides) -> SimulationConfig:
    defaults = dict(
        seed=7,
        start_time=NOW,
        duration_minutes=600,
        num_merchants=20,
        num_drivers=60,
        num_customers=500,
        base_order_rate_per_minute=1.5,
        map_size_km=14.0,
        driver_offline_probability_per_tick=0.004,
        merchant_stockout_probability=0.05,
        customer_unreachable_probability=0.04,
        perishable_spoilage_probability_per_tick=0.08,
        rush_hour_windows=(RushHourWindow(60, 200, 1.8, 0.65),),
    )
    defaults.update(overrides)
    return SimulationConfig(**defaults)


class TestRunExperiment:
    def test_produces_all_three_strategies(self):
        result = run_experiment(make_config(), threshold=40.0)
        assert set(result.metrics_by_strategy) == {
            StrategyName.NO_INTERVENTION,
            StrategyName.THRESHOLD_BASED,
            StrategyName.EXPECTED_VALUE,
        }

    def test_metrics_internally_consistent(self):
        result = run_experiment(make_config(), threshold=40.0)
        for metrics in result.metrics_by_strategy.values():
            assert (
                metrics.delivered_count
                + metrics.failed_count
                + metrics.cancelled_count
                + metrics.in_flight_count
                == metrics.total_orders
            )
            assert 0 <= metrics.late_rate <= 1
            assert 0 <= metrics.failure_rate <= 1
            assert 0 <= metrics.cancellation_rate <= 1
            assert 0 <= metrics.intervention_rate <= 1
            assert metrics.total_intervention_cost >= 0
            assert metrics.p50_delay_minutes <= metrics.p95_delay_minutes

    def test_no_intervention_strategy_never_intervenes(self):
        result = run_experiment(make_config(), threshold=40.0)
        metrics = result.metrics_by_strategy[StrategyName.NO_INTERVENTION]
        assert metrics.intervention_count == 0
        assert metrics.total_intervention_cost == 0.0

    def test_expected_value_intervenes_at_least_as_often_as_threshold_generally(self):
        # Not a strict law (RNG diverges once outcomes change), but with this
        # scenario's parameters the expected-value engine considers many more
        # low-cost levers (NOTIFY_CUSTOMER, UPDATE_ETA) than the single fixed
        # threshold action, so it should intervene on more orders.
        result = run_experiment(make_config(), threshold=40.0)
        threshold_metrics = result.metrics_by_strategy[StrategyName.THRESHOLD_BASED]
        ev_metrics = result.metrics_by_strategy[StrategyName.EXPECTED_VALUE]
        assert ev_metrics.intervention_count > threshold_metrics.intervention_count

    def test_interventions_have_a_measurable_causal_effect_on_outcomes(self):
        # With this seed/config (driver-constrained: 60 drivers vs. a
        # sustained ~1.5 orders/min with a rush-hour surge), extending
        # patience for at-risk orders (via apply_intervention_effect)
        # measurably reduces NO_DRIVER_AVAILABLE cancellations relative to
        # the no-intervention baseline — proof the intervention feedback
        # loop actually changes ground-truth outcomes, not just bookkeeping.
        result = run_experiment(make_config(), threshold=40.0)
        baseline = result.metrics_by_strategy[StrategyName.NO_INTERVENTION]
        threshold_metrics = result.metrics_by_strategy[StrategyName.THRESHOLD_BASED]
        assert threshold_metrics.intervention_count > 0
        assert threshold_metrics.total_intervention_cost > 0
        no_driver_baseline = baseline.cancellation_reason_counts.get("no_driver_available", 0)
        no_driver_threshold = threshold_metrics.cancellation_reason_counts.get(
            "no_driver_available", 0
        )
        assert no_driver_threshold < no_driver_baseline

    def test_reproducible_given_same_config(self):
        result_a = run_experiment(make_config(), threshold=40.0)
        result_b = run_experiment(make_config(), threshold=40.0)
        for strategy in StrategyName:
            m_a = result_a.metrics_by_strategy[strategy]
            m_b = result_b.metrics_by_strategy[strategy]
            assert m_a.total_orders == m_b.total_orders
            assert m_a.delivered_count == m_b.delivered_count
            assert m_a.failed_count == m_b.failed_count
            assert m_a.cancelled_count == m_b.cancelled_count
            assert m_a.total_intervention_cost == m_b.total_intervention_cost
