"""
Recommendation / Decision Intelligence Engine
===============================================
Converts the outputs of the risk engine into concrete, prioritized actions.
Pure rules engine (IF/THEN) on top of model outputs -- deliberately NOT a
black box, since operational recommendations need to be auditable by the
humans who'll act on them.

Each recommendation carries: issue, evidence, risk, recommended action,
expected benefit, urgency, and supporting metrics -- exactly the structure
required for this to be usable by a non-technical ops manager.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)


def sku_recommendations(sku_risk: list[dict], panel: pd.DataFrame, products: pd.DataFrame) -> list[dict]:
    recs = []
    for row in sku_risk:
        prob = row["stockout_probability"]
        band = row["risk_band"]
        if band not in ("High", "Critical"):
            continue
        urgency = "Immediate" if band == "Critical" else "This week"
        product_row = products[products.sku == row["sku"]]
        unit_price = float(product_row["unit_price"].values[0]) if len(product_row) else 0
        expected_units_at_risk = round(50 * prob, 0)  # illustrative -- one week of typical reorder exposure scaled by probability
        recs.append({
            "type": "Inventory Replenishment",
            "issue": f"{row['sku']} at {row['warehouse']} has a {prob:.0%} probability of stockout next week ({band} risk).",
            "evidence": row["evidence"],
            "risk_band": band,
            "recommended_action": "Trigger immediate replenishment order and review reorder point for this SKU-warehouse pair.",
            "expected_business_benefit": f"Avoid an estimated ₹{expected_units_at_risk * unit_price:,.0f} in at-risk revenue "
                                          f"if the stockout materializes as forecast.",
            "urgency": urgency,
            "supporting_metrics": {"stockout_probability": prob, "sku": row["sku"], "warehouse": row["warehouse"]},
        })
    return recs


def supplier_recommendations(supplier_risk: list[dict]) -> list[dict]:
    recs = []
    for row in supplier_risk:
        score = row["risk_score"]
        band = row["risk_band"]
        if band not in ("High", "Critical"):
            continue
        urgency = "Immediate" if band == "Critical" else "This month"
        action = ("Initiate formal supplier review and evaluate qualified alternate suppliers for the affected SKUs."
                  if band == "Critical" else
                  "Schedule a supplier performance review meeting and request a corrective action plan.")
        recs.append({
            "type": "Supplier Review",
            "issue": f"{row['supplier_name']} has a risk score of {score}/100 ({band}).",
            "evidence": row["evidence"],
            "risk_band": band,
            "recommended_action": action,
            "expected_business_benefit": "Reduces downstream stockout and late-delivery risk for all SKUs sourced from this supplier.",
            "urgency": urgency,
            "supporting_metrics": {"risk_score": score, "supplier_name": row["supplier_name"]},
        })
    return recs


def excess_inventory_recommendations(conn) -> list[dict]:
    df = pd.read_sql("""
        SELECT p.sku, w.warehouse_name, AVG(f.days_of_supply) avg_dos, AVG(f.inventory_on_hand) avg_inv, p.unit_cost
        FROM fact_inventory_snapshot f
        JOIN dim_product p ON p.product_id = f.product_id
        JOIN dim_warehouse w ON w.warehouse_id = f.warehouse_id
        GROUP BY p.product_id, w.warehouse_id
        HAVING avg_dos > 15
        ORDER BY avg_dos DESC LIMIT 10
    """, conn)
    recs = []
    for _, row in df.iterrows():
        tied_up = row["avg_inv"] * row["unit_cost"]
        recs.append({
            "type": "Inventory Reallocation",
            "issue": f"{row['sku']} at {row['warehouse_name']} is carrying {row['avg_dos']:.0f} days of supply "
                     f"(well above the network median).",
            "evidence": [f"Average inventory on hand: {row['avg_inv']:.0f} units, tying up ~₹{tied_up:,.0f} in working capital."],
            "risk_band": "Medium",
            "recommended_action": "Evaluate reallocating excess stock to higher-demand warehouses or reducing next reorder quantity.",
            "expected_business_benefit": f"Potential to free up ~₹{tied_up * cfg.HOLDING_COST_RATE_ANNUAL:,.0f}/year in holding costs.",
            "urgency": "This month",
            "supporting_metrics": {"avg_days_of_supply": round(float(row["avg_dos"]), 1), "sku": row["sku"]},
        })
    return recs


def main():
    from src.ingestion.load_raw import get_connection

    sku_risk = json.loads((cfg.PROCESSED_DIR / "unified_sku_risk.json").read_text())
    supplier_risk = json.loads((cfg.PROCESSED_DIR / "unified_supplier_risk.json").read_text())
    panel = pd.read_csv(cfg.PROCESSED_DIR / "weekly_panel.csv", parse_dates=["week"])
    products = pd.read_csv(cfg.SYNTHETIC_DIR / "dim_product.csv")
    conn = get_connection()

    recs = []
    recs += sku_recommendations(sku_risk, panel, products)
    recs += supplier_recommendations(supplier_risk)
    recs += excess_inventory_recommendations(conn)
    conn.close()

    urgency_rank = {"Immediate": 0, "This week": 1, "This month": 2}
    recs = sorted(recs, key=lambda r: urgency_rank.get(r["urgency"], 99))

    with open(cfg.PROCESSED_DIR / "recommendations.json", "w") as f:
        json.dump(recs, f, indent=2)

    log.info(f"Generated {len(recs)} recommendations "
              f"({sum(r['urgency']=='Immediate' for r in recs)} Immediate, "
              f"{sum(r['urgency']=='This week' for r in recs)} This-week, "
              f"{sum(r['urgency']=='This month' for r in recs)} This-month).")
    print(json.dumps(recs[:3], indent=2))


if __name__ == "__main__":
    main()
