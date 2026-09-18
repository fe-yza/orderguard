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


class TestOrderEndpoint:
    def test_order_detail_has_timeline_and_risk(self, db_session):
        body = _create_experiment(seed=107)
        run_id = body["simulation_run_id"]
        orders = client.get(f"/simulations/{run_id}/orders", params={"limit": 1}).json()
        order_id = orders[0]["id"]

        response = client.get(f"/orders/{order_id}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["id"] == order_id
        assert len(detail["events"]) > 0
        assert len(detail["risk_assessments"]) > 0
        assert len(detail["intervention_decisions"]) > 0

    def test_unknown_order_404s(self, db_session):
        response = client.get("/orders/does-not-exist")
        assert response.status_code == 404
