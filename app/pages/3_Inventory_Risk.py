import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from config import config as cfg

st.set_page_config(page_title="Inventory Risk — SupplyIQ", page_icon="📦", layout="wide")
st.title("📦 Inventory Intelligence")

path = cfg.PROCESSED_DIR / "unified_sku_risk.json"
if not path.exists():
    st.warning("Run `python -m src.risk_engine.unified_risk` first.")
    st.stop()

data = json.loads(path.read_text())
df = pd.DataFrame(data)

col1, col2 = st.columns([1, 3])
with col1:
    band_filter = st.multiselect("Risk band", options=["Low", "Medium", "High", "Critical"],
                                  default=["High", "Critical"])
    category_filter = st.multiselect("Category", options=sorted(df["category"].unique()), default=[])

filtered = df[df.risk_band.isin(band_filter)]
if category_filter:
    filtered = filtered[filtered.category.isin(category_filter)]
filtered = filtered.sort_values("stockout_probability", ascending=False)

with col2:
    st.subheader(f"{len(filtered)} SKU-warehouse combinations at risk")
    st.dataframe(filtered[["sku", "category", "warehouse", "stockout_probability", "risk_band"]],
                 use_container_width=True, hide_index=True)

st.divider()
st.subheader("Investigate a Specific SKU-Warehouse")
options = (filtered["sku"] + " @ " + filtered["warehouse"]).tolist()
if options:
    choice = st.selectbox("Select", options=options)
    sku_sel, wh_sel = choice.split(" @ ")
    row = filtered[(filtered.sku == sku_sel) & (filtered.warehouse == wh_sel)].iloc[0]
    st.metric("Stockout Probability (next week)", f"{row['stockout_probability']:.0%}", row["risk_band"])
    st.markdown("**Root-Cause Evidence (computed from the data):**")
    for e in row["evidence"]:
        st.markdown(f"- {e}")
else:
    st.info("No rows match the current filters.")

st.divider()
st.subheader("Excess Inventory / Slow Movers")
from src.ingestion.load_raw import get_connection
conn = get_connection()
excess = pd.read_sql("""
    SELECT p.sku, w.warehouse_name, AVG(f.days_of_supply) avg_dos, AVG(f.inventory_on_hand) avg_inv, p.unit_cost,
           AVG(f.inventory_on_hand)*p.unit_cost as tied_up_capital
    FROM fact_inventory_snapshot f
    JOIN dim_product p ON p.product_id=f.product_id
    JOIN dim_warehouse w ON w.warehouse_id=f.warehouse_id
    GROUP BY p.product_id, w.warehouse_id HAVING avg_dos > 12
    ORDER BY tied_up_capital DESC LIMIT 20
""", conn)
conn.close()
st.dataframe(excess, use_container_width=True, hide_index=True)
