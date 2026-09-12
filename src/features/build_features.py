"""
Feature Engineering
====================
Builds two model-ready datasets from the warehouse tables:

1. `weekly_product_warehouse_panel` -- a (product, warehouse, week) panel with
   demand, rolling demand statistics, inventory position, and supplier
   reliability features. This is the base table for BOTH the demand
   forecasting model and the stockout-risk classifier (they're two views of
   the same panel: predict next week's demand vs. predict next week's
   stockout).
2. `supplier_monthly_features` -- a (supplier, month) panel of reliability
   metrics used by the supplier risk model.

All features are computed using only information available *as of* the
snapshot time (lagged/rolling windows), to avoid leakage into the
forecasting and risk models trained downstream.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.utils.logger import get_logger

log = get_logger(__name__)


def build_weekly_panel() -> pd.DataFrame:
    conn = get_connection()
    orders = pd.read_sql("""
        SELECT o.order_date, o.product_id, o.warehouse_id, o.supplier_id, o.order_qty,
               o.order_status, o.is_late, p.is_seasonal, p.category, p.base_daily_demand,
               s.base_lead_time_days, s.lead_time_volatility, s.base_otif_rate, s.defect_rate
        FROM fact_orders o
        JOIN dim_product p ON p.product_id = o.product_id
        JOIN dim_supplier s ON s.supplier_id = o.supplier_id
    """, conn)
    inv = pd.read_sql("SELECT * FROM fact_inventory_snapshot", conn)
    conn.close()

    orders["order_date"] = pd.to_datetime(orders["order_date"])
    orders["week"] = orders["order_date"].dt.to_period("W").apply(lambda p: p.start_time)
    orders["is_stockout"] = orders["order_status"].astype(str).str.strip().str.lower().eq("stockout")
    orders["is_partial"] = orders["order_status"].astype(str).str.strip().str.lower().eq("partial")

    panel = orders.groupby(["product_id", "warehouse_id", "week"]).agg(
        demand_qty=("order_qty", "sum"),
        order_count=("order_qty", "count"),
        stockout_orders=("is_stockout", "sum"),
        partial_orders=("is_partial", "sum"),
        late_orders=("is_late", "sum"),
        supplier_id=("supplier_id", "first"),
        base_lead_time_days=("base_lead_time_days", "first"),
        lead_time_volatility=("lead_time_volatility", "first"),
        base_otif_rate=("base_otif_rate", "first"),
        defect_rate=("defect_rate", "first"),
        is_seasonal=("is_seasonal", "first"),
        category=("category", "first"),
    ).reset_index()

    panel["stockout_flag"] = (panel["stockout_orders"] > 0).astype(int)
    panel["any_risk_flag"] = ((panel["stockout_orders"] + panel["partial_orders"]) > 0).astype(int)

    # Merge nearest inventory snapshot (monthly cadence) as-of each week
    inv["snapshot_date"] = pd.to_datetime(inv["snapshot_date"])
    inv_sorted = inv.sort_values("snapshot_date")
    panel = panel.sort_values("week")
    merged = pd.merge_asof(
        panel.sort_values("week"),
        inv_sorted[["snapshot_date", "product_id", "warehouse_id", "inventory_on_hand", "reorder_point", "days_of_supply"]]
            .sort_values("snapshot_date"),
        left_on="week", right_on="snapshot_date",
        by=["product_id", "warehouse_id"], direction="backward",
    )

    # Time-ordered lag / rolling features PER (product, warehouse) -- critical:
    # sort by week within each group before computing lags to avoid leakage.
    merged = merged.sort_values(["product_id", "warehouse_id", "week"])
    grp = merged.groupby(["product_id", "warehouse_id"])
    merged["demand_lag_1"] = grp["demand_qty"].shift(1)
    merged["demand_lag_2"] = grp["demand_qty"].shift(2)
    merged["demand_roll4_mean"] = grp["demand_qty"].transform(lambda s: s.shift(1).rolling(4).mean())
    merged["demand_roll4_std"] = grp["demand_qty"].transform(lambda s: s.shift(1).rolling(4).std())
    merged["demand_roll8_mean"] = grp["demand_qty"].transform(lambda s: s.shift(1).rolling(8).mean())
    merged["demand_pct_change"] = grp["demand_qty"].transform(lambda s: s.shift(1).pct_change())
    merged["days_of_supply"] = grp["days_of_supply"].transform(lambda s: s.ffill())
    merged["inventory_on_hand"] = grp["inventory_on_hand"].transform(lambda s: s.ffill())
    merged["week_of_year"] = merged["week"].dt.isocalendar().week.astype(int)
    merged["month"] = merged["week"].dt.month

    # Target for stockout model: NEXT week's stockout flag (predicting the future, not describing the present)
    merged["target_stockout_next_week"] = grp["stockout_flag"].shift(-1)
    merged["target_demand_next_week"] = grp["demand_qty"].shift(-1)

    return merged


def build_supplier_monthly_features() -> pd.DataFrame:
    conn = get_connection()
    perf = pd.read_sql("SELECT * FROM fact_supplier_performance", conn)
    dim_supplier = pd.read_sql("SELECT * FROM dim_supplier", conn)
    conn.close()

    perf["performance_month"] = pd.to_datetime(perf["performance_month"])
    perf = perf.sort_values(["supplier_id", "performance_month"])
    grp = perf.groupby("supplier_id")

    perf["otif_roll3"] = grp["otif_rate"].transform(lambda s: s.shift(1).rolling(3).mean())
    perf["lead_time_roll3"] = grp["avg_lead_time_days"].transform(lambda s: s.shift(1).rolling(3).mean())
    perf["lead_time_change"] = grp["avg_lead_time_days"].transform(lambda s: s.pct_change())
    perf["otif_change"] = grp["otif_rate"].transform(lambda s: s.pct_change())

    perf = perf.merge(dim_supplier[["supplier_id", "is_single_source", "onboarded_year"]], on="supplier_id")
    return perf


def main():
    log.info("Building weekly product-warehouse panel...")
    panel = build_weekly_panel()
    panel.to_csv(cfg.PROCESSED_DIR / "weekly_panel.csv", index=False)
    log.info(f"weekly_panel.csv: {len(panel):,} rows, {panel['product_id'].nunique()} products, "
              f"stockout rate (any week) = {panel['stockout_flag'].mean():.3f}")

    log.info("Building supplier monthly feature set...")
    sup = build_supplier_monthly_features()
    sup.to_csv(cfg.PROCESSED_DIR / "supplier_monthly_features.csv", index=False)
    log.info(f"supplier_monthly_features.csv: {len(sup):,} rows")


if __name__ == "__main__":
    main()
