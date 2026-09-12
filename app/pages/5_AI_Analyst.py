import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from config import config as cfg
from src.llm.ai_analyst import ask

st.set_page_config(page_title="AI Analyst — SupplyIQ", page_icon="🤖", layout="wide")
st.title("🤖 AI Supply Chain Analyst")

mode = "LLM-backed" if (cfg.LLM_PROVIDER in ("anthropic", "openai") and cfg.LLM_API_KEY) else "Local fallback (no API key configured)"
st.caption(f"Grounded on live analytics output · Mode: **{mode}**")

if mode.startswith("Local"):
    st.info("No LLM_API_KEY is set in .env — running in local template mode. The answer structure and grounding "
            "logic are identical; add an API key to LLM_PROVIDER/LLM_API_KEY in .env for natural-language synthesis.")

examples = [
    "Why is supplier risk increasing?",
    "Which SKUs are most likely to stock out?",
    "What caused today's risk increase?",
    "Which supplier should management investigate first?",
    "What are the biggest inventory inefficiencies?",
    "What action should operations take this week?",
    "What is the estimated financial impact of current risks?",
]

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

st.markdown("**Example questions:**")
cols = st.columns(len(examples) // 2 + 1)
for i, ex in enumerate(examples):
    if cols[i % len(cols)].button(ex, key=f"ex_{i}"):
        st.session_state.pending_question = ex

question = st.chat_input("Ask about suppliers, SKUs, inventory, or risk...") or st.session_state.pop("pending_question", None)

if question:
    with st.spinner("Retrieving grounded context and generating answer..."):
        result = ask(question)
    st.session_state.chat_history.append(result)

for r in reversed(st.session_state.chat_history):
    with st.chat_message("user"):
        st.write(r["question"])
    with st.chat_message("assistant"):
        st.markdown(r["answer"])
        st.caption(f"mode: {r['mode']} · matched intents: {', '.join(r['matched_intents'])}")
