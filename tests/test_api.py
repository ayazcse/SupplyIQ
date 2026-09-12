"""API tests using FastAPI's TestClient -- no live server required.
Assumes the pipeline has already been run (database + processed artifacts exist),
matching how these tests would run in CI after the data/build stage."""
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("ok", "degraded")


def test_kpis_endpoint_returns_expected_fields():
    resp = client.get("/kpis")
    assert resp.status_code == 200
    data = resp.json()
    for field in ["total_orders", "otif_rate", "fill_rate", "stockout_rate", "total_revenue_simulated"]:
        assert field in data


def test_suppliers_risk_endpoint():
    resp = client.get("/suppliers/risk")
    assert resp.status_code == 200
    assert "suppliers" in resp.json()


def test_suppliers_risk_band_filter_only_returns_matching_band():
    resp = client.get("/suppliers/risk?band=High")
    assert resp.status_code == 200
    data = resp.json()
    assert all(s["risk_band"] == "High" for s in data["suppliers"])


def test_inventory_risk_endpoint():
    resp = client.get("/inventory/risk")
    assert resp.status_code == 200
    assert "items" in resp.json()


def test_recommendations_endpoint():
    resp = client.get("/recommendations")
    assert resp.status_code == 200
    assert "recommendations" in resp.json()


def test_ask_endpoint_returns_structured_answer():
    resp = client.post("/ask", json={"question": "Which SKUs are most likely to stock out?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "INSIGHT" in data["answer"]
    assert "RECOMMENDATION" in data["answer"]


def test_analyze_endpoint_404_for_unknown_entity():
    resp = client.post("/analyze", json={"entity_type": "sku", "entity_id": "SKU-DOES-NOT-EXIST"})
    assert resp.status_code == 404


def test_analyze_endpoint_400_for_invalid_type():
    resp = client.post("/analyze", json={"entity_type": "widget", "entity_id": "x"})
    assert resp.status_code == 400
