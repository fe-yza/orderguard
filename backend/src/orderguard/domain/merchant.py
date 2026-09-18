"""Merchant entity.

Prep time is the merchant-side source of delay risk: `base_prep_minutes` and
`prep_time_stddev_minutes` model normal variance, `rush_hour_multiplier`
models the environment factor (time of day), and `active_order_backlog` is
mutated by the simulation engine as orders queue up — a merchant with a
growing backlog gets slower, which is exactly the kind of observable,
non-random signal the risk engine will key off of later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orderguard.domain.geo import Point


@dataclass(slots=True)
class Merchant:
    id: str
    name: str
    location: Point
    base_prep_minutes: float
    prep_time_stddev_minutes: float
    rush_hour_multiplier: float
    reliability_score: float
    """Probability-scaling factor in [0, 1]; lower means more prone to
    stockouts (cancellations) and prep delays. Not a probability itself."""

    active_order_backlog: int = field(default=0)

    def __post_init__(self) -> None:
        if not 0.0 <= self.reliability_score <= 1.0:
            raise ValueError(f"reliability_score must be in [0, 1], got {self.reliability_score}")
        if self.base_prep_minutes <= 0:
            raise ValueError(f"base_prep_minutes must be > 0, got {self.base_prep_minutes}")
        if self.prep_time_stddev_minutes < 0:
            raise ValueError(
                f"prep_time_stddev_minutes must be >= 0, got {self.prep_time_stddev_minutes}"
            )
        if self.rush_hour_multiplier <= 0:
            raise ValueError(f"rush_hour_multiplier must be > 0, got {self.rush_hour_multiplier}")

    def expected_prep_minutes(self, *, is_rush_hour: bool) -> float:
        """Mean prep time under current conditions, before per-order noise.

        Backlog penalty is linear and capped implicitly by callers via the
        simulation's tick size — a merchant with 10 queued orders takes
        meaningfully longer per order than one with none, which is the
        realistic dynamic we want (busy merchants get slower and riskier).
        """
        backlog_penalty = 1.0 + 0.08 * self.active_order_backlog
        rush_penalty = self.rush_hour_multiplier if is_rush_hour else 1.0
        return self.base_prep_minutes * backlog_penalty * rush_penalty
