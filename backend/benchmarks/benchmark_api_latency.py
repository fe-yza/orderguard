"""API latency benchmark against a *running* server (real HTTP, real Postgres
round trips — not FastAPI's in-process TestClient, which skips actual
socket I/O). Requires the API already running, e.g.:

    PYTHONPATH=src .venv/bin/uvicorn orderguard.api.app:app --port 8000

Run: PYTHONPATH=src .venv/bin/python benchmarks/benchmark_api_latency.py
"""

from __future__ import annotations

import statistics
import time

import httpx

BASE_URL = "http://127.0.0.1:8000"
N_REQUESTS = 50


def _config(seed: int, num_orders_target: int) -> dict:
    rate = num_orders_target / 300
    return {
        "seed": seed,
        "start_time": "2026-01-01T08:00:00",
        "duration_minutes": 300,
        "num_merchants": max(5, int(rate * 8)),
        "num_drivers": max(10, int(rate * 12)),
        "num_customers": max(50, int(rate * 120)),
        "base_order_rate_per_minute": rate,
        "map_size_km": 10.0,
    }


def _timed(client: httpx.Client, method: str, path: str, **kwargs) -> float:
    t0 = time.perf_counter()
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return (time.perf_counter() - t0) * 1000


def _percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100)
    lower, upper = int(k), min(int(k) + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (k - lower)


def report(name: str, samples: list[float]) -> None:
    print(
        f"{name:35s} p50={_percentile(samples, 50):7.1f}ms "
        f"p95={_percentile(samples, 95):7.1f}ms "
        f"mean={statistics.fmean(samples):7.1f}ms  n={len(samples)}"
    )


def main() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        create_latencies = [
            _timed(
                client,
                "POST",
                "/simulations",
                json={"config": _config(seed=1000 + i, num_orders_target=1000), "threshold": 40.0},
            )
            for i in range(5)
        ]
        report("POST /simulations (~1K orders)", create_latencies)

        # A larger run to exercise list/detail endpoints against a
        # realistically-sized dataset.
        response = client.post(
            "/simulations",
            json={"config": _config(seed=2, num_orders_target=5000), "threshold": 40.0},
        )
        response.raise_for_status()
        run_id = response.json()["simulation_run_id"]
        order_ids = [
            o["id"] for o in client.get(f"/simulations/{run_id}/orders?limit=20").json()
        ]

        report(
            "GET /simulations",
            [_timed(client, "GET", "/simulations?limit=50") for _ in range(N_REQUESTS)],
        )
        report(
            "GET /simulations/{id}/orders",
            [
                _timed(client, "GET", f"/simulations/{run_id}/orders?limit=100")
                for _ in range(N_REQUESTS)
            ],
        )
        report(
            "GET /simulations/{id}/high-risk",
            [
                _timed(client, "GET", f"/simulations/{run_id}/high-risk?min_score=0")
                for _ in range(N_REQUESTS)
            ],
        )
        report(
            "GET /simulations/{id}/metrics",
            [
                _timed(client, "GET", f"/simulations/{run_id}/metrics")
                for _ in range(N_REQUESTS)
            ],
        )
        report(
            "GET /simulations/{id}/map",
            [_timed(client, "GET", f"/simulations/{run_id}/map") for _ in range(N_REQUESTS)],
        )
        report(
            "GET /simulations/{id}/orders/{id}",
            [
                _timed(
                    client,
                    "GET",
                    f"/simulations/{run_id}/orders/{order_ids[i % len(order_ids)]}",
                )
                for i in range(N_REQUESTS)
            ],
        )


if __name__ == "__main__":
    main()
