# LinkedIn Content

## Launch Post

I kept seeing the same pattern in my own projects: build a dashboard, show
some charts, call it done. So for this one I asked a harder question —
what would it actually take to go from raw data to a decision a manager
could act on?

That became SupplyIQ: a supply chain risk platform built around four
questions real operations teams ask — what's happening, why, what's likely
to happen next, and what should we do about it.

A few things I made sure were real, not just claimed:

→ The synthetic dataset (170K+ orders, 60 suppliers, 120 SKUs, 3 years) is
driven by an actual weekly demand/inventory/replenishment simulation, not
random sampling — stockouts happen because simulated inventory ran out, not
because I flipped a weighted coin.

→ I deliberately injected two "shock events" (a supplier lead-time
collapse and a demand surge) into the simulation, then checked that my own
models actually caught them. They did — one supplier's lead time jumped
from ~7 to ~13 days and its risk score spiked in exactly the injected
window.

→ The stockout risk model's ROC-AUC is a modest 0.67, and I wrote that
down honestly instead of tuning the writeup to sound better — a chunk of
the demand variation is stochastic by design, and a suspiciously high AUC
would actually mean my validation was leaking.

→ The "AI analyst" only ever explains numbers it retrieved from real
computed data first — it has a local, no-API-key fallback mode specifically
so the grounding logic is checkable without needing an LLM key at all.

Stack: Python, SQL (22 hand-written analytics queries), LightGBM, FastAPI,
Streamlit, Power BI/DAX, pytest (34 passing tests), Docker.

Repo: [link]
Everything in the README is something I actually ran — including the
things I couldn't fully test (Docker, a live Postgres instance, an LLM API
key), which I called out rather than glossing over.

## Short Project Description (for LinkedIn "Projects" section)

**SupplyIQ — AI-Powered Supply Chain Risk & Decision Intelligence Platform**
End-to-end data engineering, SQL analytics, and ML platform simulating a
mid-size distribution business (170K+ orders, 60 suppliers, 120 SKUs).
Combines a validated data pipeline, 22 advanced SQL queries, 4 ML models
(demand forecasting, stockout risk, supplier risk, anomaly detection) with
documented time-series validation, a rules-based recommendation engine, a
grounded GenAI analyst, and a Power BI dashboard — surfaced via FastAPI and
Streamlit. 34 automated tests. Full architecture, model cards, and stated
limitations documented in the repo.
