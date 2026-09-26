"""Minimal in-memory rate limiting for the one genuinely expensive endpoint
(POST /simulations, which runs three full simulation passes per request).

This is a single-process, best-effort limiter -- correct and sufficient for
a small public demo running one backend instance, per the project's
simplest-implementation-first principle. It is not a distributed rate
limiter: if OrderGuard ever ran multiple backend replicas, each would track
its own counters, so a client could get up to N requests through per
replica. That tradeoff is acceptable here and would need a shared store
(e.g. Redis) to fix, which is exactly the kind of infrastructure this
project defers until it's demonstrably needed.
"""

from __future__ import annotations

import time
from collections import defaultdict
from functools import lru_cache
from threading import Lock

from fastapi import HTTPException, Request, status

from orderguard.api.settings import get_app_settings


class SlidingWindowRateLimiter:
    """Tracks request timestamps per key and rejects once more than
    `max_requests` have landed within the trailing `window_seconds`."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self._window_seconds
            while hits and hits[0] < cutoff:
                hits.pop(0)
            if len(hits) >= self._max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        "Too many simulation requests from this client -- "
                        "please wait a bit and try again."
                    ),
                )
            hits.append(now)


@lru_cache
def get_simulation_rate_limiter() -> SlidingWindowRateLimiter:
    settings = get_app_settings()
    return SlidingWindowRateLimiter(
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


def enforce_simulation_rate_limit(request: Request) -> None:
    """FastAPI dependency: raises 429 once the calling client (identified
    by remote address) has exceeded the configured request budget."""
    client_host = request.client.host if request.client else "unknown"
    get_simulation_rate_limiter().check(client_host)
