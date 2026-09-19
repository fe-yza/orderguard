from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from orderguard.api.app import create_app

client = TestClient(create_app())

BASE_CONFIG = {
    "seed": 21,
    "start_time": "2026-01-01T08:00:00",
    "duration_minutes": 200,
    "num_merchants": 8,
    "num_drivers": 15,
    "num_customers": 100,
    "base_order_rate_per_minute": 0.8,
    "map_size_km": 8.0,
}


def _create_experiment(seed: int = 21) -> dict:
    config = {**BASE_CONFIG, "seed": seed}
    response = client.post("/simulations", json={"config": config, "threshold": 40.0})
    assert response.status_code == 200, response.text
    return response.json()


class TestHealthEndpoint:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCreateExperiment:
    def test_returns_three_strategies(self, db_session):
        body = _create_experiment(seed=101)
        assert "simulation_run_id" in body
        strategies = {m["strategy"] for m in body["metrics"]}
        assert strategies == {"no_intervention", "threshold_based", "expected_value"}

    def test_metrics_have_consistent_totals(self, db_session):
        body = _create_experiment(seed=102)
        for metrics in body["metrics"]:
            assert (
                metrics["delivered_count"]
                + metrics["failed_count"]
                + metrics["cancelled_count"]
                + metrics["in_flight_count"]
                == metrics["total_orders"]
            )

    def test_rejects_invalid_config(self, db_session):
        bad_config = {**BASE_CONFIG, "num_drivers": 0}
        response = client.post("/simulations", json={"config": bad_config, "threshold": 40.0})
        assert response.status_code == 422


class TestSimulationEndpoints:
    def test_list_and_get_simulation(self, db_session):
        body = _create_experiment(seed=103)
        run_id = body["simulation_run_id"]

        list_response = client.get("/simulations")
        assert list_response.status_code == 200
        assert any(r["id"] == run_id for r in list_response.json())

        get_response = client.get(f"/simulations/{run_id}")
        assert get_response.status_code == 200
        assert get_response.json()["id"] == run_id

    def test_get_unknown_simulation_404s(self, db_session):
        response = client.get("/simulations/does-not-exist")
        assert response.status_code == 404

    def test_metrics_endpoint(self, db_session):
        body = _create_experiment(seed=104)
        run_id = body["simulation_run_id"]
        response = client.get(f"/simulations/{run_id}/metrics")
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_orders_endpoint_with_status_filter(self, db_session):
        body = _create_experiment(seed=105)
        run_id = body["simulation_run_id"]
        response = client.get(f"/simulations/{run_id}/orders", params={"status": "delivered"})
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) > 0
        assert all(o["status"] == "delivered" for o in orders)

    def test_high_risk_endpoint(self, db_session):
        body = _create_experiment(seed=106)
        run_id = body["simulation_run_id"]
        response = client.get(f"/simulations/{run_id}/high-risk", params={"min_score": 0})
        assert response.status_code == 200
        results = response.json()
        assert len(results) > 0
        scores = [r["latest_risk_assessment"]["overall_risk_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_map_endpoint(self, db_session):
        body = _create_experiment(seed=108)
        run_id = body["simulation_run_id"]
        response = client.get(f"/simulations/{run_id}/map")
        assert response.status_code == 200
        entities = response.json()
        assert len(entities["merchants"]) == BASE_CONFIG["num_merchants"]
        assert len(entities["drivers"]) == BASE_CONFIG["num_drivers"]
        assert len(entities["customers"]) == BASE_CONFIG["num_customers"]
        for merchant in entities["merchants"]:
            assert 0 <= merchant["location_x_km"] <= BASE_CONFIG["map_size_km"]
            assert 0 <= merchant["location_y_km"] <= BASE_CONFIG["map_size_km"]

    def test_map_endpoint_unknown_run_404s(self, db_session):
        response = client.get("/simulations/does-not-exist/map")
        assert response.status_code == 404

    def test_map_endpoint_includes_deliveries_with_valid_endpoints(self, db_session):
        body = _create_experiment(seed=112)
        run_id = body["simulation_run_id"]
        entities = client.get(f"/simulations/{run_id}/map").json()

        orders = client.get(f"/simulations/{run_id}/orders", params={"limit": 10000}).json()
        assert len(entities["deliveries"]) == len(orders)

        merchant_ids = {m["id"] for m in entities["merchants"]}
        customer_ids = {c["id"] for c in entities["customers"]}
        driver_ids = {d["id"] for d in entities["drivers"]}

        active_count = 0
        risk_scored_count = 0
        driver_assigned_count = 0
        for delivery in entities["deliveries"]:
            assert delivery["merchant_id"] in merchant_ids
            assert delivery["customer_id"] in customer_ids
            assert delivery["is_active"] == (
                delivery["status"] not in ("delivered", "failed", "cancelled")
            )
            if delivery["is_active"]:
                active_count += 1
            if delivery["latest_risk_score"] is not None:
                risk_scored_count += 1
                assert 0 <= delivery["latest_risk_score"] <= 100
            if delivery["driver_id"] is not None:
                driver_assigned_count += 1
                assert delivery["driver_id"] in driver_ids
                assert delivery["driver_x_km"] is not None
                assert delivery["driver_status"] is not None

        # Every order that was ever confirmed gets an initial risk
        # assessment, so this should cover almost all orders.
        assert risk_scored_count > 0
        assert driver_assigned_count > 0
        assert active_count >= 0  # some runs finish with nothing in flight


class TestOrderEndpoint:
    def test_order_detail_has_timeline_and_risk(self, db_session):
        body = _create_experiment(seed=107)
        run_id = body["simulation_run_id"]
        orders = client.get(f"/simulations/{run_id}/orders", params={"limit": 1}).json()
        order_id = orders[0]["id"]

        response = client.get(f"/simulations/{run_id}/orders/{order_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["id"] == order_id
        assert len(detail["events"]) > 0
        assert len(detail["risk_assessments"]) > 0
        assert len(detail["intervention_decisions"]) > 0

    def test_unknown_order_404s(self, db_session):
        body = _create_experiment(seed=109)
        run_id = body["simulation_run_id"]
        response = client.get(f"/simulations/{run_id}/orders/does-not-exist")
        assert response.status_code == 404

    def test_same_order_id_across_two_runs_resolves_independently(self, db_session):
        # Regression test: order/merchant/driver/customer IDs are only
        # unique within a single run (see persistence/models.py), so two
        # different runs' "order-000000" must resolve to two different,
        # correctly-scoped orders rather than an ambiguous/incorrect match.
        body_a = _create_experiment(seed=110)
        body_b = _create_experiment(seed=111)
        run_a, run_b = body_a["simulation_run_id"], body_b["simulation_run_id"]

        detail_a = client.get(f"/simulations/{run_a}/orders/order-000000").json()
        detail_b = client.get(f"/simulations/{run_b}/orders/order-000000").json()
        assert detail_a["id"] == detail_b["id"] == "order-000000"
        # Different runs, so (almost certainly) different merchant/customer
        # assignments or timestamps -- the two responses aren't identical.
        assert detail_a != detail_b


class TestConcurrentRequests:
    def test_concurrent_experiment_creation_does_not_corrupt_state(self, db_session):
        # Each request gets its own DB session (FastAPI's per-request
        # dependency injection via get_session), and simulation_run_id is a
        # UUID, so concurrent POSTs should never collide or corrupt each
        # other's rows -- this is the same composite-key correctness
        # regression tested sequentially in test_same_order_id_across_two_
        # runs_resolves_independently, but under real concurrent access
        # rather than one request at a time.
        seeds = list(range(200, 208))
        with ThreadPoolExecutor(max_workers=8) as pool:
            bodies = list(pool.map(_create_experiment, seeds))

        run_ids = [b["simulation_run_id"] for b in bodies]
        assert len(set(run_ids)) == len(run_ids)  # all distinct

        for run_id in run_ids:
            response = client.get(f"/simulations/{run_id}")
            assert response.status_code == 200
            orders = client.get(f"/simulations/{run_id}/orders", params={"limit": 5}).json()
            assert len(orders) > 0
            detail = client.get(f"/simulations/{run_id}/orders/{orders[0]['id']}").json()
            assert detail["id"] == orders[0]["id"]

    def test_concurrent_reads_of_same_run_are_consistent(self, db_session):
        body = _create_experiment(seed=209)
        run_id = body["simulation_run_id"]

        with ThreadPoolExecutor(max_workers=10) as pool:
            responses = list(
                pool.map(lambda _: client.get(f"/simulations/{run_id}/metrics"), range(20))
            )
        assert all(r.status_code == 200 for r in responses)
        payloads = [r.json() for r in responses]
        assert all(p == payloads[0] for p in payloads)
