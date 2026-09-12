"""Tests for src/validation/data_quality.py -- uses small synthetic frames
so the rule LOGIC is verified in isolation, independent of the full dataset."""
import pandas as pd

from src.validation.data_quality import score_from_results, RuleResult


def test_score_perfect_data_is_100():
    results = [RuleResult("rule_a", 100, 0, 0.0, "CRITICAL", "n/a")]
    assert score_from_results(results) == 100.0


def test_score_penalizes_critical_more_than_low():
    # Same total failure magnitude, but concentrated on a CRITICAL rule vs a LOW
    # rule -- weighted blend should push the CRITICAL-heavy scenario lower.
    critical_heavy = [
        RuleResult("rule_a", 100, 50, 50.0, "CRITICAL", "n/a"),
        RuleResult("rule_b", 100, 0, 0.0, "LOW", "n/a"),
    ]
    low_heavy = [
        RuleResult("rule_a", 100, 0, 0.0, "CRITICAL", "n/a"),
        RuleResult("rule_b", 100, 50, 50.0, "LOW", "n/a"),
    ]
    assert score_from_results(critical_heavy) < score_from_results(low_heavy)


def test_score_bounded_between_0_and_100():
    results = [RuleResult("rule_a", 100, 100, 100.0, "CRITICAL", "n/a")]
    score = score_from_results(results)
    assert 0.0 <= score <= 100.0


def test_score_is_average_when_all_pass():
    results = [
        RuleResult("r1", 100, 0, 0.0, "CRITICAL", "n/a"),
        RuleResult("r2", 100, 0, 0.0, "LOW", "n/a"),
    ]
    assert score_from_results(results) == 100.0
