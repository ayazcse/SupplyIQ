"""
SupplyIQ — Streamlit Application (Home / Executive Dashboard)
Run with: streamlit run app/Home.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from config import config as cfg
from src.ingestion.load_raw import get_connection

st.set_page_config(page_title="SupplyIQ", page_icon="📦", layout="wide")


@st.cache_data(ttl=300)
def load_kpis():
    conn = get_connection()
    total_orders = pd.read_sql("SELECT COUNT(*) c FROM fact_orders", conn).c[0]
    otif = pd.read_sql("SELECT AVG(CASE WHEN is_late=0 THEN 1.0 ELSE 0.0 END) v FROM fact_orders", conn).v[0]
    fill_rate = pd.read_sql(
        "SELECT AVG(CASE WHEN LOWER(TRIM(order_status))='fulfilled' THEN 1.0 ELSE 0.0 END) v FROM fact_orders", conn).v[0]
    stockout_rate = pd.read_sql(
        "SELECT AVG(CASE WHEN LOWER(TRIM(order_status))='stockout' THEN 1.0 ELSE 0.0 END) v FROM fact_orders", conn).v[0]
    revenue = pd.read_sql("SELECT SUM(revenue) v FROM fact_orders", conn).v[0]
    avg_lead = pd.read_sql("SELECT AVG(avg_lead_time_days) v FROM fact_supplier_performance", conn).v[0]
    monthly_risk = pd.read_sql("""
        SELECT strftime('%Y-%m', order_date) ym,
               100.0*SUM(CASE WHEN LOWER(TRIM(order_status))='stockout' OR is_late=1 THEN 1 ELSE 0 END)/COUNT(*) risk_pct
        FROM fact_orders GROUP BY ym ORDER BY ym
    """, conn)
    regional = pd.read_sql("""
        SELECT r.region_name, 100.0*SUM(CASE WHEN LOWER(TRIM(o.order_status))='stockout' THEN 1 ELSE 0 END)/COUNT(*) stockout_pct
        FROM fact_orders o JOIN dim_region r ON r.region_id=o.region_id GROUP BY r.region_name
    """, conn)
    conn.close()
    return dict(total_orders=total_orders, otif=otif, fill_rate=fill_rate, stockout_rate=stockout_rate,
                revenue=revenue, avg_lead=avg_lead, monthly_risk=monthly_risk, regional=regional)


def load_json(name):
    path = cfg.PROCESSED_DIR / name
    return json.loads(path.read_text()) if path.exists() else []


st.title("📦 SupplyIQ — Executive Command Center")
st.caption("AI-Powered Supply Chain Risk & Decision Intelligence Platform · simulated data")

try:
    kpis = load_kpis()
except Exception as e:
    st.error(f"Could not load data: {e}. Run `python scripts/run_pipeline.py` first.")
    st.stop()

impact_path = cfg.PROCESSED_DIR / "business_impact_summary.json"
impact = json.loads(impact_path.read_text()) if impact_path.exists() else None

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Orders", f"{kpis['total_orders']:,}")
c2.metric("OTIF Rate", f"{kpis['otif']:.1%}")
c3.metric("Fill Rate", f"{kpis['fill_rate']:.1%}")
c4.metric("Stockout Rate", f"{kpis['stockout_rate']:.1%}")
c5.metric("Avg Supplier Lead Time", f"{kpis['avg_lead']:.1f} days")
c6.metric("Annual Revenue at Risk", f"₹{impact['total_estimated_annual_risk_exposure']/1e6:.1f}M" if impact else "N/A")

st.divider()
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Risk Event Rate Over Time")
    st.line_chart(kpis["monthly_risk"].set_index("ym")["risk_pct"])
    st.caption("% of orders per month that were stockouts or late deliveries.")

with col2:
    st.subheader("Regional Stockout Rate")
    st.bar_chart(kpis["regional"].set_index("region_name")["stockout_pct"])

st.divider()
col3, col4 = st.columns(2)

with col3:
    st.subheader("🚨 Top Critical Issues")
    recs = load_json("recommendations.json")
    critical = [r for r in recs if r["urgency"] == "Immediate"][:5]
    if critical:
        for r in critical:
            with st.container(border=True):
                st.markdown(f"**{r['type']}** — {r['issue']}")
                st.caption(f"→ {r['recommended_action']}")
    else:
        st.info("No immediate-urgency issues in the current run.")

with col4:
    st.subheader("🏭 Top Supplier Risks")
    sup = load_json("unified_supplier_risk.json")
    top_sup = sorted(sup, key=lambda r: -r["risk_score"])[:5]
    df = pd.DataFrame(top_sup)[["supplier_name", "risk_score", "risk_band"]] if top_sup else pd.DataFrame()
    st.dataframe(df, hide_index=True, use_container_width=True)

st.divider()
if impact:
    st.subheader("💰 Simulated Business Impact")
    st.caption(impact["disclaimer"])
    i1, i2, i3 = st.columns(3)
    i1.metric("Stockout Lost Margin / yr", f"₹{impact['stockout_impact']['estimated_annual_lost_margin']/1e6:.1f}M")
    i2.metric("Excess Inventory Holding Cost / yr", f"₹{impact['excess_inventory_cost']['estimated_annual_holding_cost_on_excess']/1e6:.1f}M")
    i3.metric("Expedite Shipping Premium / yr", f"₹{impact['expedite_premium_cost']['estimated_annual_expedite_premium']/1e6:.1f}M")

st.divider()
st.caption("Use the sidebar to navigate: Risk Monitoring · Supplier Ranking · Inventory Risk · Forecast · AI Analyst · Recommendations")
