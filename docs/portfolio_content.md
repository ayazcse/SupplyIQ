# Portfolio Website Content

## Project Title
SupplyIQ — AI-Powered Supply Chain Risk & Decision Intelligence Platform

## One-Line Description
An end-to-end data engineering, SQL analytics, machine learning, and GenAI
platform that turns raw supply chain data into prioritized, evidence-backed
business decisions.

## Detailed Description
Most portfolio dashboards describe what happened. SupplyIQ was built to
answer the four questions a supply chain manager actually asks: what's
happening, why, what's likely to happen next, and what should we do about
it. It simulates a mid-size distribution business — 120 SKUs, 22
warehouses, 60 suppliers, 3 years of realistic (not randomly generated)
transactional data — and runs it through a full pipeline: validated ETL,
a star-schema SQL warehouse, 22 advanced analytics queries, four machine
learning models with documented time-series validation, a root-cause
engine that computes evidence directly from the data, a rules-based
recommendation engine, a business-impact calculator, and a grounded GenAI
analyst — all surfaced through a FastAPI backend, a Streamlit application,
and a Power BI dashboard.

## The Challenge
Building something that would hold up to real interview scrutiny, not just
look impressive at a glance. That meant: making the synthetic data
causally coherent (stockouts happen *because* simulated inventory ran out,
not because of an independent random flag), validating every ML model with
proper time-based splits instead of a random shuffle that would leak the
future, reporting model limitations honestly (a modest ROC-AUC, clearly
explained, rather than an inflated one), and building a GenAI layer that
is structurally incapable of inventing numbers rather than just prompted
to avoid it.

## Solution
A 16-stage orchestrated pipeline (`scripts/run_pipeline.py`) that runs in
about two minutes end to end: synthetic data generation → ingestion →
validation → cleaning → SQL analytics → feature engineering → four ML
models → a unified risk engine with computed root-cause evidence → a
recommendation engine → a business impact calculator → a grounded AI
analyst → automated tests. Every stage's output is a versioned artifact
the next stage reads, so the whole system is auditable end to end.

## Tech Stack
Python (Pandas, NumPy, scikit-learn, LightGBM, statsmodels) · SQL (SQLite,
with a documented PostgreSQL schema alternative) · FastAPI · Streamlit ·
Power BI / DAX · pytest · Docker

## Key Features
- 170,000+ simulated orders driven by a real weekly demand/inventory
  simulation, with two deliberately injected "shock events" that the
  pipeline verifiably detects.
- A 14-rule automated data quality engine (99.9% score) with genuine
  injected issues (nulls, duplicates, sign errors, inconsistent labels) to
  catch.
- 22 hand-written SQL analytics queries (window functions, CTEs, rolling
  metrics), all automatically validated on every pipeline run.
- 4 ML models — demand forecasting, stockout risk, supplier risk, anomaly
  detection — each with a documented model card (objective, features,
  validation strategy, metrics, and honestly stated limitations).
- A root-cause engine that computes real before/after evidence from the
  data rather than generating templated explanations.
- A grounded GenAI analyst that can only reference retrieved, real
  computed data — with a fully functional local fallback mode requiring
  zero API keys.
- 34 automated tests (data integrity, business logic, API contracts), all
  passing.

## Business Impact
A documented, assumption-transparent financial model estimating ₹238M in
annual supply chain risk exposure (stockouts, excess inventory, expedited
freight) on the simulated dataset — built to demonstrate the *method* an
analyst would apply to real company data, clearly labeled as
estimated/simulated throughout.

## Screenshots
[Add your own after running `streamlit run app/Home.py` — suggested shots:
Executive Command Center KPIs, the Supplier Risk explainability view
showing top risk drivers, and the AI Analyst chat interface.]

## GitHub CTA
View the full source, architecture docs, and model cards on GitHub → [link]

## Demo CTA
Run it yourself in under 5 minutes: `.\scripts\setup.ps1` then
`.\scripts\run_pipeline.ps1` then `.\scripts\start_app.ps1` → [link to repo]
