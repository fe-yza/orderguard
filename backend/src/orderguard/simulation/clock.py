"""Simulated wall-clock time.

A thin wrapper rather than raw `datetime` arithmetic scattered through the
engine — it's the one place "how far into the run are we" is computed, which
the config's rush-hour windows and the risk engine's "how long has this been
pending" calculations both need consistently.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(slots=True)
class SimClock:
    start_time: datetime
    current_time: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.current_time is None:
            self.current_time = self.start_time

    @property
    def minute_of_run(self) -> int:
        return int((self.current_time - self.start_time).total_seconds() // 60)

    def advance(self, minutes: int) -> None:
        self.current_time += timedelta(minutes=minutes)
