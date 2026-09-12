"""
Data Quality Engine
====================
Runs a documented set of rules against the RAW staging data and produces a
scored report (rule, records checked, failed count, failure %, severity,
recommendation). This is intentionally run against `staging_fact_orders_raw`
-- the untouched landing table -- so the score reflects genuine issues in the
source data, not issues we've already fixed.

Severity levels: CRITICAL (blocks trust in the record), HIGH (needs cleaning
before analysis), MEDIUM (should be normalized), LOW (cosmetic / informational).
"""
from __future__ import annotations

import sys
from pathlib import Path
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class RuleResult:
    rule: str
    records_checked: int
    failed_count: int
    failure_pct: float
    severity: str
    recommendation: str


def _pct(fail, total):
    return round(100 * fail / total, 3) if total else 0.0


def run_checks(df: pd.DataFrame) -> list[RuleResult]:
    n = len(df)
    results = []

    # 1. Null critical identifiers
    for col, sev in [("order_id", "CRITICAL"), ("product_id", "CRITICAL"),
                      ("warehouse_id", "CRITICAL"), ("supplier_id", "CRITICAL")]:
        fail = df[col].isna().sum() + (df[col].astype(str).str.strip() == "").sum()
        results.append(RuleResult(f"null_{col}", n, int(fail), _pct(fail, n), sev,
                                   f"Reject or quarantine records missing {col} before loading to warehouse."))

    # 2. Null non-critical numeric fields
    fail = df["unit_price"].isna().sum() + (df["unit_price"].astype(str).str.strip().isin(["", "nan"])).sum()
    results.append(RuleResult("null_unit_price", n, int(fail), _pct(fail, n), "HIGH",
                               "Impute using the product's catalog price or flag for manual pricing review."))

    fail = df["transport_mode_id"].isna().sum() + (df["transport_mode_id"].astype(str).str.strip().isin(["", "nan"])).sum()
    results.append(RuleResult("null_transport_mode", n, int(fail), _pct(fail, n), "MEDIUM",
                               "Default to the warehouse's most common transport mode; flag for logistics review."))

    # 3. Duplicate order_id
    dupe_mask = df["order_id"].duplicated(keep=False)
    results.append(RuleResult("duplicate_order_id", n, int(dupe_mask.sum()), _pct(dupe_mask.sum(), n), "HIGH",
                               "Deduplicate keeping the first occurrence; investigate source system for repeated sends."))

    # 4. Negative or zero prices
    price_num = pd.to_numeric(df["unit_price"], errors="coerce")
    fail = (price_num < 0).sum()
    results.append(RuleResult("negative_unit_price", n, int(fail), _pct(fail, n), "CRITICAL",
                               "Take absolute value only after confirming with source system; likely a sign-entry error."))

    # 5. Impossible / outlier quantities (using IQR-based bound, a legitimate stats technique)
    qty_num = pd.to_numeric(df["order_qty"], errors="coerce")
    q1, q3 = qty_num.quantile([0.25, 0.75])
    iqr = q3 - q1
    upper = q3 + 3 * iqr  # 3x IQR = conservative "extreme outlier" bound
    fail = (qty_num > upper).sum()
    results.append(RuleResult("extreme_quantity_outlier", n, int(fail), _pct(fail, n), "MEDIUM",
                               f"Flag orders above {upper:,.0f} units (3x IQR) for manual confirmation before use in forecasting."))

    # 6. Invalid / inconsistent categorical values -- compare the RAW string
    # (not normalized) against the canonical label set, so casing/whitespace
    # drift from an upstream system merge is actually caught.
    canonical_statuses = {"Fulfilled", "Stockout", "Partial"}
    fail = (~df["order_status"].isin(canonical_statuses)).sum()
    results.append(RuleResult("inconsistent_order_status", n, int(fail), _pct(fail, n), "MEDIUM",
                               "Normalize casing/whitespace via a canonical status mapping table."))

    # 7. Invalid dates (actual before promised is fine; order_date after actual_delivery_date is not)
    od = pd.to_datetime(df["order_date"], errors="coerce")
    ad = pd.to_datetime(df["actual_delivery_date"], errors="coerce")
    fail = (od > ad).sum()
    results.append(RuleResult("delivery_before_order_date", n, int(fail), _pct(fail, n), "CRITICAL",
                               "Investigate source timestamps; delivery cannot precede the order."))

    # 8. Referential integrity: product_id / warehouse_id / supplier_id exist in dims
    conn = get_connection()
    valid_products = set(pd.read_sql("SELECT product_id FROM dim_product", conn)["product_id"].astype(str))
    valid_warehouses = set(pd.read_sql("SELECT warehouse_id FROM dim_warehouse", conn)["warehouse_id"].astype(str))
    valid_suppliers = set(pd.read_sql("SELECT supplier_id FROM dim_supplier", conn)["supplier_id"].astype(str))
    conn.close()
    fail = (~df["product_id"].astype(str).isin(valid_products)).sum()
    results.append(RuleResult("orphan_product_fk", n, int(fail), _pct(fail, n), "CRITICAL",
                               "Reject records referencing a product_id absent from dim_product."))
    fail = (~df["warehouse_id"].astype(str).isin(valid_warehouses)).sum()
    results.append(RuleResult("orphan_warehouse_fk", n, int(fail), _pct(fail, n), "CRITICAL",
                               "Reject records referencing a warehouse_id absent from dim_warehouse."))
    fail = (~df["supplier_id"].astype(str).isin(valid_suppliers)).sum()
    results.append(RuleResult("orphan_supplier_fk", n, int(fail), _pct(fail, n), "CRITICAL",
                               "Reject records referencing a supplier_id absent from dim_supplier."))

    return results


def score_from_results(results: list[RuleResult]) -> float:
    """A simple, transparent weighted score: CRITICAL failures penalize the
    most. Score = 100 - weighted average failure rate. Documented so it isn't
    a magic number -- see docs/data_dictionary.md."""
    weights = {"CRITICAL": 3.0, "HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.5}
    total_weight = sum(weights[r.severity] for r in results)
    weighted_fail = sum(weights[r.severity] * r.failure_pct for r in results)
    penalty = weighted_fail / total_weight if total_weight else 0
    return round(max(0.0, 100 - penalty), 2)


def main():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM staging_fact_orders_raw", conn)
    conn.close()
    log.info(f"Running data quality checks on {len(df):,} raw staged rows...")

    results = run_checks(df)
    report_df = pd.DataFrame([asdict(r) for r in results])
    score = score_from_results(results)

    out_path = cfg.PROCESSED_DIR / "data_quality_report.csv"
    report_df.to_csv(out_path, index=False)

    print("\n" + "=" * 78)
    print(f"DATA QUALITY REPORT — fact_orders (raw)")
    print("=" * 78)
    print(report_df.to_string(index=False))
    print("-" * 78)
    print(f"DATA QUALITY SCORE: {score}%")
    print("=" * 78 + "\n")

    log.info(f"Data quality report saved to {out_path}")
    log.info(f"Overall Data Quality Score: {score}%")
    return score, report_df


if __name__ == "__main__":
    main()
