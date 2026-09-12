"""Tests for risk-band mapping and rule-based supplier scoring logic."""
import pandas as pd

from src.models.stockout_risk_model import band_from_prob
from src.models.supplier_risk_model import rule_based_score, band_from_score


def test_stockout_band_boundaries():
    assert band_from_prob(0.0) == "Low"
    assert band_from_prob(0.24) == "Low"
    assert band_from_prob(0.25) == "Medium"
    assert band_from_prob(0.5) == "High"
    assert band_from_prob(0.8) == "Critical"
    assert band_from_prob(0.99) == "Critical"


def test_supplier_band_boundaries():
    assert band_from_score(0) == "Low"
    assert band_from_score(29) == "Low"
    assert band_from_score(30) == "Moderate"
    assert band_from_score(55) == "High"
    assert band_from_score(80) == "Critical"
    assert band_from_score(100) == "Critical"


def test_rule_based_score_increases_with_worse_otif():
    good = pd.Series({"otif_rate": 0.98, "defect_rate_observed": 0.01, "avg_lead_time_days": 5,
                       "lead_time_change": 0, "is_single_source": False, "cost_variance_pct": 2})
    bad = pd.Series({"otif_rate": 0.40, "defect_rate_observed": 0.01, "avg_lead_time_days": 5,
                      "lead_time_change": 0, "is_single_source": False, "cost_variance_pct": 2})
    assert rule_based_score(bad) > rule_based_score(good)


def test_rule_based_score_bounded_0_to_100():
    worst_case = pd.Series({"otif_rate": 0.0, "defect_rate_observed": 1.0, "avg_lead_time_days": 100,
                             "lead_time_change": 5, "is_single_source": True, "cost_variance_pct": 500})
    score = rule_based_score(worst_case)
    assert 0 <= score <= 100


def test_single_source_flag_increases_score():
    base = {"otif_rate": 0.9, "defect_rate_observed": 0.01, "avg_lead_time_days": 5,
            "lead_time_change": 0, "cost_variance_pct": 2}
    single = pd.Series({**base, "is_single_source": True})
    multi = pd.Series({**base, "is_single_source": False})
    assert rule_based_score(single) > rule_based_score(multi)
