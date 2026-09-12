"""
Risk Engine
============
Combines the outputs of the stockout-risk model, supplier-risk model, and
anomaly detector into ONE unified view, and generates evidence-backed
root-cause explanations -- the "why is this happening" layer that sits
between raw model outputs and the recommendation engine.

This module does NOT invent explanations: every root-cause bullet is
computed directly from before/after comparisons in the actual data
(e.g., "SKU demand increased 31%" is a real percentage computed from the
weekly panel, not a templated guess).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)


def load_all():
    stockout = pd.read_csv(cfg.PROCESSED_DIR / "stockout_risk_predictions.csv", parse_dates=["week"])
    supplier = pd.read_csv(cfg.PROCESSED_DIR / "supplier_risk_full_history.csv", parse_dates=["performance_month"])
    panel = pd.read_csv(cfg.PROCESSED_DIR / "weekly_panel.csv", parse_dates=["week"])
    anomalies = pd.read_csv(cfg.PROCESSED_DIR / "anomalies_detected.csv", parse_dates=["week"])
    products = pd.read_csv(cfg.SYNTHETIC_DIR / "dim_product.csv")
    warehouses = pd.read_csv(cfg.SYNTHETIC_DIR / "dim_warehouse.csv")
    suppliers = pd.read_csv(cfg.SYNTHETIC_DIR / "dim_supplier.csv")
    return stockout, supplier, panel, anomalies, products, warehouses, suppliers


def build_sku_root_cause(panel: pd.DataFrame, product_id: int, warehouse_id: int, as_of_week: pd.Timestamp) -> dict:
    """Compares the most recent 4 weeks to the prior 4 weeks for a specific
    (product, warehouse) to produce genuine, computed root-cause evidence."""
    sub = panel[(panel.product_id == product_id) & (panel.warehouse_id == warehouse_id)].sort_values("week")
    sub = sub[sub.week <= as_of_week]
    if len(sub) < 8:
        return {"evidence": ["Insufficient history (<8 weeks) to compute a reliable trend comparison."]}

    recent = sub.tail(4)
    prior = sub.iloc[-8:-4]
    evidence = []

    demand_recent, demand_prior = recent["demand_qty"].mean(), prior["demand_qty"].mean()
    if demand_prior > 0:
        pct = 100 * (demand_recent - demand_prior) / demand_prior
        if abs(pct) > 10:
            evidence.append(f"Demand {'increased' if pct > 0 else 'decreased'} {abs(pct):.0f}% "
                             f"({demand_prior:.0f} -> {demand_recent:.0f} units/week, trailing 4wk vs prior 4wk).")

    dos_recent, dos_prior = recent["days_of_supply"].mean(), prior["days_of_supply"].mean()
    if pd.notna(dos_recent) and pd.notna(dos_prior) and dos_prior > 0:
        pct = 100 * (dos_recent - dos_prior) / dos_prior
        if abs(pct) > 10:
            evidence.append(f"Inventory coverage {'improved' if pct > 0 else 'declined'} from "
                             f"{dos_prior:.1f} to {dos_recent:.1f} days of supply.")

    late_recent, late_prior = recent["late_orders"].sum(), prior["late_orders"].sum()
    if late_recent > late_prior and late_prior >= 0:
        evidence.append(f"Late deliveries for this product-warehouse rose from {int(late_prior)} to {int(late_recent)} "
                         f"orders over the last 4 weeks.")

    stockout_recent, stockout_prior = recent["stockout_orders"].sum(), prior["stockout_orders"].sum()
    if stockout_recent > stockout_prior:
        evidence.append(f"Stockout-flagged orders increased from {int(stockout_prior)} to {int(stockout_recent)} "
                         f"in the same comparison window.")

    if not evidence:
        evidence.append("No material week-over-week deviation found in demand, inventory coverage, or delivery reliability "
                         "for this product-warehouse in the most recent comparison window.")
    return {"evidence": evidence,
            "recent_demand": round(float(demand_recent), 1), "prior_demand": round(float(demand_prior), 1),
            "recent_days_of_supply": round(float(dos_recent), 1) if pd.notna(dos_recent) else None}


def build_supplier_root_cause(supplier_hist: pd.DataFrame, supplier_id: int) -> dict:
    sub = supplier_hist[supplier_hist.supplier_id == supplier_id].sort_values("performance_month")
    if len(sub) < 4:
        return {"evidence": ["Insufficient history (<4 months) for this supplier."]}
    recent = sub.tail(2)
    prior = sub.iloc[-4:-2]
    evidence = []

    otif_recent, otif_prior = recent["otif_rate"].mean(), prior["otif_rate"].mean()
    if otif_prior > 0:
        pct = 100 * (otif_recent - otif_prior) / otif_prior
        if abs(pct) > 8:
            evidence.append(f"OTIF {'improved' if pct > 0 else 'deteriorated'} {abs(pct):.0f}% "
                             f"({otif_prior:.1%} -> {otif_recent:.1%}, trailing 2mo vs prior 2mo).")

    lead_recent, lead_prior = recent["avg_lead_time_days"].mean(), prior["avg_lead_time_days"].mean()
    if lead_prior > 0:
        pct = 100 * (lead_recent - lead_prior) / lead_prior
        if abs(pct) > 8:
            evidence.append(f"Average lead time {'increased' if pct > 0 else 'decreased'} from "
                             f"{lead_prior:.1f} to {lead_recent:.1f} days ({pct:+.0f}%).")

    if not evidence:
        evidence.append("No material change in this supplier's OTIF or lead time over the recent comparison window.")
    return {"evidence": evidence}


def build_unified_risk_table():
    stockout, supplier, panel, anomalies, products, warehouses, suppliers = load_all()

    latest_week = stockout["week"].max()
    latest_stockout = stockout[stockout.week == latest_week].copy()
    latest_stockout = latest_stockout.merge(products[["product_id", "sku", "category"]], on="product_id")
    latest_stockout = latest_stockout.merge(warehouses[["warehouse_id", "warehouse_name"]], on="warehouse_id")

    rows = []
    for _, r in latest_stockout.iterrows():
        rc = build_sku_root_cause(panel, r["product_id"], r["warehouse_id"], latest_week)
        rows.append({
            "entity_type": "SKU-Warehouse", "sku": r["sku"], "category": r["category"],
            "warehouse": r["warehouse_name"], "week": str(r["week"].date()),
            "stockout_probability": round(float(r["stockout_probability"]), 3),
            "risk_band": r["risk_band"], "evidence": rc["evidence"],
        })
    sku_risk = pd.DataFrame(rows)
    sku_risk.to_json(cfg.PROCESSED_DIR / "unified_sku_risk.json", orient="records", indent=2)

    latest_month = supplier["performance_month"].max()
    latest_sup = supplier[supplier.performance_month == latest_month].copy()
    rows = []
    for _, r in latest_sup.iterrows():
        rc = build_supplier_root_cause(supplier, r["supplier_id"])
        rows.append({
            "entity_type": "Supplier", "supplier_name": r["supplier_name"],
            "month": str(r["performance_month"].date()),
            "risk_score": round(float(r["rule_based_risk_score"]), 1),
            "risk_band": r["risk_band"], "evidence": rc["evidence"],
        })
    supplier_risk = pd.DataFrame(rows)
    supplier_risk.to_json(cfg.PROCESSED_DIR / "unified_supplier_risk.json", orient="records", indent=2)

    log.info(f"Unified risk table built: {len(sku_risk):,} SKU-warehouse rows (week {latest_week.date()}), "
              f"{len(supplier_risk):,} supplier rows (month {latest_month.date()})")
    log.info(f"Critical/High SKU risk count: {(sku_risk.risk_band.isin(['Critical','High'])).sum()}")
    log.info(f"Critical/High supplier risk count: {(supplier_risk.risk_band.isin(['Critical','High'])).sum()}")

    return sku_risk, supplier_risk


if __name__ == "__main__":
    build_unified_risk_table()
