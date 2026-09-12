import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from config import config as cfg

st.set_page_config(page_title="Recommendations — SupplyIQ", page_icon="✅", layout="wide")
st.title("✅ AI Recommendations")

path = cfg.PROCESSED_DIR / "recommendations.json"
if not path.exists():
    st.warning("Run `python -m src.recommendations.recommendation_engine` first.")
    st.stop()

recs = json.loads(path.read_text())

urgency_filter = st.multiselect("Urgency", options=["Immediate", "This week", "This month"],
                                 default=["Immediate", "This week", "This month"])
type_filter = st.multiselect("Type", options=sorted(set(r["type"] for r in recs)), default=[])

filtered = [r for r in recs if r["urgency"] in urgency_filter]
if type_filter:
    filtered = [r for r in filtered if r["type"] in type_filter]

st.subheader(f"{len(filtered)} recommendations")

badge_color = {"Immediate": "🔴", "This week": "🟠", "This month": "🟡"}
for r in filtered:
    with st.container(border=True):
        st.markdown(f"{badge_color.get(r['urgency'], '⚪')} **{r['type']}** — *{r['urgency']}*")
        st.markdown(f"**Issue:** {r['issue']}")
        st.markdown(f"**Recommended Action:** {r['recommended_action']}")
        st.markdown(f"**Expected Benefit:** {r['expected_business_benefit']}")
        with st.expander("Evidence"):
            for e in r["evidence"]:
                st.markdown(f"- {e}")
