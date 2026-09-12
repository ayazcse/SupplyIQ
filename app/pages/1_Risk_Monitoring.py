import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from config import config as cfg
from src.ingestion.load_raw import get_connection

st.set_page_config(page_title="Risk Monitoring — SupplyIQ", page_icon="🚨", layout="wide")
st.title("🚨 Risk Monitoring")

tab1, tab2 = st.tabs(["Anomalies", "Risk Trend"])

with tab1:
    st.subheader("Detected Anomalies (Isolation Forest + Rolling Z-Score)")
    path = cfg.PROCESSED_DIR / "anomalies_detected.csv"
    if path.exists():
        df = pd.read_csv(path)
        search = st.text_input("Filter by product_id or warehouse_id (optional)")
        if search:
            try:
                pid = int(search)
                df = df[(df.product_id == pid) | (df.warehouse_id == pid)]
            except ValueError:
                pass
        st.dataframe(df.sort_values("week", ascending=False), use_container_width=True, hide_index=True)
        st.caption(f"{len(df):,} anomalies flagged across the simulation horizon.")
    else:
        st.warning("Run the anomaly detection pipeline first.")

with tab2:
    st.subheader("Monthly Risk Event Rate (Stockouts + Late Deliveries)")
    conn = get_connection()
    df = pd.read_sql("""
        SELECT strftime('%Y-%m', order_date) ym,
               COUNT(*) total_orders,
               SUM(CASE WHEN LOWER(TRIM(order_status))='stockout' OR is_late=1 THEN 1 ELSE 0 END) risk_events
        FROM fact_orders GROUP BY ym ORDER BY ym
    """, conn)
    conn.close()
    df["risk_rate_pct"] = 100 * df["risk_events"] / df["total_orders"]
    st.line_chart(df.set_index("ym")["risk_rate_pct"])
    st.dataframe(df, use_container_width=True, hide_index=True)
