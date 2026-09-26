import time

import pytest
from fastapi import HTTPException

from orderguard.api.rate_limit import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    def test_allows_requests_within_budget(self):
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.check("client-a")  # should not raise

    def test_rejects_once_budget_exhausted(self):
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        limiter.check("client-a")
        limiter.check("client-a")
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("client-a")
        assert exc_info.value.status_code == 429

    def test_tracks_each_key_independently(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
        limiter.check("client-a")
        limiter.check("client-b")  # different key, its own fresh budget

    def test_old_hits_fall_out_of_the_window(self):
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=0.05)
        limiter.check("client-a")
        time.sleep(0.1)
        limiter.check("client-a")  # earlier hit has aged out of the window


class TestSimulationEndpointRateLimit:
    """End-to-end check that POST /simulations actually enforces the
    configured budget, not just the limiter class in isolation."""

    def test_returns_429_once_budget_exhausted(self, monkeypatch, db_session):
        from fastapi.testclient import TestClient

        from orderguard.api import rate_limit, settings
        from orderguard.api.app import create_app

        small_config = {
            "seed": 900,
            "start_time": "2026-01-01T08:00:00",
            "duration_minutes": 30,
            "num_merchants": 2,
            "num_drivers": 3,
            "num_customers": 10,
            "base_order_rate_per_minute": 0.5,
            "map_size_km": 5.0,
        }

        monkeypatch.setenv("ORDERGUARD_RATE_LIMIT_MAX_REQUESTS", "1")
        settings.get_app_settings.cache_clear()
        rate_limit.get_simulation_rate_limiter.cache_clear()
        try:
            tight_client = TestClient(create_app())
            body = {"config": small_config, "threshold": 40.0}
            first = tight_client.post("/simulations", json=body)
            assert first.status_code == 200
            second = tight_client.post("/simulations", json=body)
            assert second.status_code == 429
        finally:
            settings.get_app_settings.cache_clear()
            rate_limit.get_simulation_rate_limiter.cache_clear()
