import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from config import config as cfg

st.set_page_config(page_title="Demand Forecast — SupplyIQ", page_icon="📈", layout="wide")
st.title("📈 Demand Intelligence")

path = cfg.PROCESSED_DIR / "forecast_actual_vs_predicted.csv"
card_path = cfg.PROCESSED_DIR / "forecast_model_card.json"
if not path.exists():
    st.warning("Run `python -m src.forecasting.demand_forecast` first.")
    st.stop()

df = pd.read_csv(path, parse_dates=["week"])
card = json.loads(card_path.read_text()) if card_path.exists() else {}

st.subheader("Model Comparison")
comp_path = cfg.PROCESSED_DIR / "forecast_model_comparison.csv"
if comp_path.exists():
    st.dataframe(pd.read_csv(comp_path), hide_index=True, use_container_width=True)
    st.caption(f"Validation strategy: {card.get('validation_strategy', 'time-based split')}")

st.divider()
products = sorted(df["product_id"].unique())
warehouses_for_product = None
c1, c2 = st.columns(2)
with c1:
    pid = st.selectbox("Product ID", options=products)
sub_wh = sorted(df[df.product_id == pid]["warehouse_id"].unique())
with c2:
    wid = st.selectbox("Warehouse ID", options=sub_wh)

plot_df = df[(df.product_id == pid) & (df.warehouse_id == wid)].sort_values("week")
st.subheader(f"Actual vs Predicted Demand — Product {pid}, Warehouse {wid}")
chart_df = plot_df.set_index("week")[["target_demand_next_week", "predicted_demand", "baseline_predicted_demand"]]
chart_df.columns = ["Actual", "LightGBM Predicted", "Baseline Predicted"]
st.line_chart(chart_df)

st.divider()
st.subheader("Feature Importance")
fi_path = cfg.PROCESSED_DIR / "forecast_feature_importance.csv"
if fi_path.exists():
    fi = pd.read_csv(fi_path)
    st.bar_chart(fi.set_index("feature")["importance"])

with st.expander("Model Card"):
    st.json(card)
