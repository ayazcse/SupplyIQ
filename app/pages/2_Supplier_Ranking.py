import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from config import config as cfg

st.set_page_config(page_title="Supplier Ranking — SupplyIQ", page_icon="🏭", layout="wide")
st.title("🏭 Supplier Intelligence")

path = cfg.PROCESSED_DIR / "supplier_risk_latest.json"
if not path.exists():
    st.warning("Run `python -m src.models.supplier_risk_model` first.")
    st.stop()

data = json.loads(path.read_text())
df = pd.DataFrame(data)

band_filter = st.multiselect("Filter by risk band", options=["Low", "Moderate", "High", "Critical"],
                              default=["High", "Critical"])
filtered = df[df.risk_band.isin(band_filter)].sort_values("rule_based_risk_score", ascending=False)

st.subheader(f"{len(filtered)} suppliers matching filter")
st.dataframe(
    filtered[["supplier_name", "rule_based_risk_score", "risk_band", "otif_rate", "avg_lead_time_days",
              "defect_rate_observed", "is_single_source"]],
    use_container_width=True, hide_index=True,
)

st.divider()
st.subheader("Explain a Supplier's Risk Score")
selected = st.selectbox("Choose a supplier", options=df["supplier_name"].tolist())
row = df[df.supplier_name == selected].iloc[0]

c1, c2 = st.columns([1, 2])
with c1:
    st.metric("Risk Score", f"{row['rule_based_risk_score']}/100", row["risk_band"])
    st.metric("OTIF", f"{row['otif_rate']:.1%}")
    st.metric("Avg Lead Time", f"{row['avg_lead_time_days']:.1f} days")
    st.metric("Defect Rate", f"{row['defect_rate_observed']:.2%}")

with c2:
    st.markdown("**Top Risk Drivers (explainability)**")
    drivers = row["top_drivers"]
    if drivers:
        drv_df = pd.DataFrame(drivers)
        st.bar_chart(drv_df.set_index("driver")["contribution"])
        st.dataframe(drv_df, hide_index=True, use_container_width=True)
    else:
        st.info("No significant risk drivers for this supplier.")
