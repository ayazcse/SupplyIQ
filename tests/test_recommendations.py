"""Tests for src/recommendations/recommendation_engine.py rule logic."""
import pandas as pd

from src.recommendations.recommendation_engine import sku_recommendations, supplier_recommendations


def test_sku_recommendations_only_for_high_and_critical():
    sku_risk = [
        {"sku": "SKU-1", "warehouse": "WH-1", "stockout_probability": 0.9, "risk_band": "Critical", "evidence": ["e1"]},
        {"sku": "SKU-2", "warehouse": "WH-1", "stockout_probability": 0.1, "risk_band": "Low", "evidence": []},
    ]
    products = pd.DataFrame({"sku": ["SKU-1", "SKU-2"], "unit_price": [10.0, 5.0]})
    recs = sku_recommendations(sku_risk, pd.DataFrame(), products)
    assert len(recs) == 1
    assert recs[0]["supporting_metrics"]["sku"] == "SKU-1"


def test_sku_recommendation_urgency_mapping():
    sku_risk = [
        {"sku": "SKU-1", "warehouse": "WH-1", "stockout_probability": 0.9, "risk_band": "Critical", "evidence": []},
        {"sku": "SKU-2", "warehouse": "WH-1", "stockout_probability": 0.6, "risk_band": "High", "evidence": []},
    ]
    products = pd.DataFrame({"sku": ["SKU-1", "SKU-2"], "unit_price": [10.0, 5.0]})
    recs = sku_recommendations(sku_risk, pd.DataFrame(), products)
    urgencies = {r["supporting_metrics"]["sku"]: r["urgency"] for r in recs}
    assert urgencies["SKU-1"] == "Immediate"
    assert urgencies["SKU-2"] == "This week"


def test_every_recommendation_has_required_fields():
    sku_risk = [{"sku": "SKU-1", "warehouse": "WH-1", "stockout_probability": 0.9, "risk_band": "Critical", "evidence": ["e"]}]
    products = pd.DataFrame({"sku": ["SKU-1"], "unit_price": [10.0]})
    recs = sku_recommendations(sku_risk, pd.DataFrame(), products)
    required = {"type", "issue", "evidence", "risk_band", "recommended_action",
                "expected_business_benefit", "urgency", "supporting_metrics"}
    for r in recs:
        assert required.issubset(r.keys())


def test_supplier_recommendations_only_for_high_and_critical():
    supplier_risk = [
        {"supplier_name": "Acme", "risk_score": 85, "risk_band": "Critical", "evidence": ["e"]},
        {"supplier_name": "Beta", "risk_score": 20, "risk_band": "Low", "evidence": []},
    ]
    recs = supplier_recommendations(supplier_risk)
    assert len(recs) == 1
    assert recs[0]["supporting_metrics"]["supplier_name"] == "Acme"
