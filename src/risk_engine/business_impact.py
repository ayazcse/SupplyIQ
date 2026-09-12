"""
Business Impact Calculator
=============================
Translates operational risk into ESTIMATED / SIMULATED financial exposure.
Every number here is clearly labeled as an estimate built on documented
assumptions (see config.py) applied to the actual simulated dataset -- never
presented as real company results.

Three headline numbers, computed bottom-up from the data (not asserted):
- Potential annual stockout impact (lost margin from unmet demand)
- Excess inventory holding cost (capital tied up beyond healthy days-of-supply)
- Expedited shipping premium (cost of Air freight vs. its cheaper alternative)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.utils.logger import get_logger

log = get_logger(__name__)

YEARS_OF_DATA = 3.0  # SIM_START_DATE to SIM_END_DATE spans 3 calendar years


def stockout_impact(conn) -> dict:
    df = pd.read_sql("""
        SELECT o.order_qty, o.unit_price, p.unit_cost
        FROM fact_orders o JOIN dim_product p ON p.product_id = o.product_id
        WHERE LOWER(TRIM(o.order_status)) IN ('stockout','partial')
    """, conn)
    lost_revenue = (df["order_qty"] * df["unit_price"]).sum()
    lost_margin = lost_revenue * cfg.STOCKOUT_LOST_MARGIN_RATE
    annualized = lost_margin / YEARS_OF_DATA
    return {
        "lost_revenue_3yr_simulated": round(float(lost_revenue), 0),
        "assumed_margin_rate": cfg.STOCKOUT_LOST_MARGIN_RATE,
        "estimated_annual_lost_margin": round(float(annualized), 0),
    }


def excess_inventory_cost(conn) -> dict:
    df = pd.read_sql("""
        SELECT f.inventory_on_hand, f.days_of_supply, p.unit_cost
        FROM fact_inventory_snapshot f JOIN dim_product p ON p.product_id = f.product_id
    """, conn)
    healthy_dos = df["days_of_supply"].median()  # "healthy" = the network's own median, not an arbitrary constant
    excess = df[df["days_of_supply"] > healthy_dos * 2]
    excess_value = (excess["inventory_on_hand"] * excess["unit_cost"]).sum()
    annual_holding_cost = excess_value * cfg.HOLDING_COST_RATE_ANNUAL
    return {
        "healthy_days_of_supply_benchmark": round(float(healthy_dos), 1),
        "excess_inventory_value_snapshot_avg": round(float(excess_value / max(1, df['days_of_supply'].notna().sum()) * len(excess)), 0),
        "assumed_annual_holding_cost_rate": cfg.HOLDING_COST_RATE_ANNUAL,
        "estimated_annual_holding_cost_on_excess": round(float(annual_holding_cost), 0),
    }


def expedite_premium_cost(conn) -> dict:
    df = pd.read_sql("""
        SELECT sh.shipping_cost, tm.mode_name, sh.distance_km
        FROM fact_shipments sh JOIN dim_transport_mode tm ON tm.transport_mode_id = sh.transport_mode_id
    """, conn)
    air = df[df.mode_name == "Air"]
    road = df[df.mode_name == "Road"]
    air_cost_per_km = (air["shipping_cost"] / air["distance_km"]).mean()
    road_cost_per_km = (road["shipping_cost"] / road["distance_km"]).mean()
    premium_per_km = max(0, air_cost_per_km - road_cost_per_km)
    total_air_km = air["distance_km"].sum()
    annual_premium = (premium_per_km * total_air_km) / YEARS_OF_DATA
    return {
        "air_cost_per_km": round(float(air_cost_per_km), 3),
        "road_cost_per_km": round(float(road_cost_per_km), 3),
        "estimated_annual_expedite_premium": round(float(annual_premium), 0),
    }


def main():
    conn = get_connection()
    stockout = stockout_impact(conn)
    excess = excess_inventory_cost(conn)
    expedite = expedite_premium_cost(conn)
    conn.close()

    total_annual_exposure = (stockout["estimated_annual_lost_margin"] +
                              excess["estimated_annual_holding_cost_on_excess"] +
                              expedite["estimated_annual_expedite_premium"])

    summary = {
        "disclaimer": "All figures below are ESTIMATED / SIMULATED business impact derived from a synthetic "
                       "dataset using the documented assumptions in config.py. They illustrate the METHOD an "
                       "analyst would use on real company data -- they are not real financial results.",
        "stockout_impact": stockout,
        "excess_inventory_cost": excess,
        "expedite_premium_cost": expedite,
        "total_estimated_annual_risk_exposure": round(total_annual_exposure, 0),
        "estimated_recoverable_opportunity": round(total_annual_exposure * 0.4, 0),  # documented: assume ~40% is addressable via the recommendations engine's actions
    }

    with open(cfg.PROCESSED_DIR / "business_impact_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    log.info("Business impact summary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
