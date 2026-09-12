# SupplyIQ

**AI-Powered Supply Chain Risk & Decision Intelligence Platform** — an end-to-end data engineering, analytics, machine learning, and GenAI system that turns raw supply-chain transactions into prioritized business decisions.

> This project simulates a realistic mid-size distribution business (120 SKUs, 22 warehouses, 60 suppliers, 3 years of data) and answers four questions management actually asks: **What is happening? Why is it happening? What will happen next? What should we do about it?**

---

## Business Problem

Supply chain teams drown in dashboards that describe the past but rarely explain *why* something went wrong or *what to do next*. SupplyIQ closes that gap: it combines a proper analytical data model, advanced SQL, statistical/ML forecasting, explainable risk scoring, and a grounded GenAI analyst into one pipeline that ends in concrete, evidence-backed recommendations — not just charts.

## Solution

A layered pipeline: raw data → validated & cleaned warehouse tables → SQL analytics → ML models (forecasting, stockout risk, supplier risk, anomaly detection) → a risk engine that generates **computed, evidence-based root-cause explanations** → a rules-based recommendation engine → a business-impact calculator → a grounded AI analyst that answers natural-language questions using only that computed evidence → surfaced through a FastAPI backend, a Streamlit app, and a Power BI dashboard.

## Architecture

```
RAW SYNTHETIC DATA (documented simulation, not random noise)
        ↓
INGESTION (staging tables, dirty data landed as-is)
        ↓
VALIDATION (14-rule data-quality engine, scored)
        ↓
CLEANING / PREPROCESSING (deduped, normalized, imputed, outliers flagged not dropped)
        ↓
SQL DATA WAREHOUSE (SQLite star schema; 22 advanced analytics queries)
        ↓
FEATURE ENGINEERING (time-safe lag/rolling panel)
        ↓
ML MODELS (demand forecast · stockout risk · supplier risk · anomaly detection)
        ↓
RISK ENGINE (unified risk + computed root-cause evidence)
        ↓
DECISION ENGINE (rules → prioritized recommendations + business impact $)
        ↓
GENAI INSIGHT LAYER (grounded Q&A, LLM optional, local fallback always works)
        ↓
API (FastAPI) + APP (Streamlit) + DASHBOARD (Power BI)
        ↓
BUSINESS DECISION
```

See [`docs/architecture.md`](docs/architecture.md) for the full diagram and design rationale, including what's genuinely automated vs. what requires a manual step (e.g. Power BI `.pbix` authoring).

## Tech Stack

| Layer | Technology |
|---|---|
| Data generation & simulation | Python, NumPy, Pandas, Faker |
| Database | SQLite (zero-setup default) + documented PostgreSQL schema |
| SQL | 22 queries using CTEs, window functions, rolling metrics |
| ML / Forecasting | scikit-learn, LightGBM, statsmodels |
| Explainability | Feature importances + transparent rule-based scoring |
| GenAI | Grounded retrieval + Anthropic/OpenAI API (optional) with deterministic local fallback |
| API | FastAPI |
| App | Streamlit |
| BI | Power BI (star schema + DAX) |
| Testing | pytest (34 tests) |
| Containerization | Docker + docker-compose |

## Dataset

Fully synthetic but **simulated, not randomly generated** — a weekly demand/inventory/replenishment simulation drives every number, so stockouts, excess inventory, and supplier deterioration all emerge causally rather than being sampled independently. See [`docs/data_dictionary.md`](docs/data_dictionary.md) for full generation logic.

| Table | Rows (this run) |
|---|---|
| fact_orders | 170,766 |
| fact_shipments | 24,000 |
| fact_inventory_snapshot | 12,000 |
| fact_supplier_performance | 2,035 |
| dim_product | 120 |
| dim_supplier | 60 |
| dim_warehouse | 22 |
| dim_region | 10 |

Two **deliberately injected, documented events** validate that the whole pipeline actually detects real signal: a supplier lead-time/OTIF collapse (Jul–Sep 2024, two suppliers) and a demand surge (Electronics category, Q4 2024). Both are correctly picked up downstream by the supplier risk model and root-cause engine — verified, not assumed.

Realistic messiness is also deliberately injected (nulls, duplicate order IDs, negative prices, inconsistent status casing, extreme outliers) so the data-quality engine has genuine issues to catch.

## Data Pipeline

Raw → staging (dirty data landed untouched) → validated (14-rule DQ engine, **99.9% score** on this run) → cleaned (deduped, imputed, normalized, outliers flagged not silently dropped) → loaded into a SQLite star schema. Full details: [`docs/business_logic.md`](docs/business_logic.md).

## SQL Analytics

22 business queries in [`sql/analytics/business_queries.sql`](sql/analytics/business_queries.sql), each answering a specific question (top suppliers by OTIF, rolling 30-day demand, inventory turnover, demand-spike detection, working-capital exposure, etc.), using CTEs, window functions (`RANK`, `LAG`, `NTILE`, `AVG…OVER`), and conditional aggregation. All 22 are automatically executed and validated by `scripts/run_sql_queries.py` — this is checked on every pipeline run, not just written once.

## Machine Learning

| Model | Task | Validation | Result |
|---|---|---|---|
| Demand Forecast (LightGBM vs. seasonal-naive baseline) | Predict next-week demand per SKU-warehouse | Time-based split (no shuffling) | WAPE 56.3% vs. baseline 60.9% |
| Stockout Risk (LightGBM classifier) | P(stockout next week) | Time-based split, balanced classes | ROC-AUC 0.67, Recall 0.63 |
| Supplier Risk (rule-based + LightGBM regressor) | 0–100 risk score, rule-based ground truth + next-month forecast | Time-based split | R² 0.86, MAE 4.2 pts |
| Anomaly Detection (Isolation Forest + rolling z-score) | Flag unusual demand/inventory/lead-time combinations | Unsupervised | 7.3% of weekly rows flagged, each with a stated reason |

Full model cards (objective, features, validation strategy, metrics, **stated limitations**) are generated by the pipeline into `data/processed/*_model_card.json`. The stockout model's moderate AUC is deliberately reported as-is (not inflated) — see [`docs/ml_methodology.md`](docs/ml_methodology.md) for why.

## Forecasting

See the Machine Learning section above and [`docs/ml_methodology.md`](docs/ml_methodology.md) for the full time-series validation methodology (why a random train/test split would have leaked the future, and how the baseline was chosen to be a legitimate comparison rather than a strawman).

## Risk Engine

Combines stockout risk, supplier risk, and anomalies into one view, and generates **root-cause evidence computed directly from before/after comparisons in the data** (e.g., *"Demand increased 31% (…4wk vs prior 4wk)"*) — never templated guesses. See [`src/risk_engine/unified_risk.py`](src/risk_engine/unified_risk.py).

## Explainability

- Supplier risk: transparent, auditable rule-based weights (documented in [`docs/business_logic.md`](docs/business_logic.md)) plus per-supplier "top risk drivers" breakdown.
- ML models: LightGBM `feature_importances_` exported for every model.
- Every recommendation carries its supporting evidence, not just a risk number.

## GenAI

An **AI Supply Chain Analyst** that retrieves real computed context (risk scores, evidence, recommendations, business impact) *before* generating an answer, and is instructed to say "insufficient evidence" rather than invent numbers. Works with **zero API key** (deterministic local template mode) or with an Anthropic/OpenAI key for natural-language synthesis over the same grounded context. See [`docs/ai_guardrails.md`](docs/ai_guardrails.md).

## Dashboard

Power BI star-schema data model + 6-page dashboard spec + full DAX measure library in [`docs/powerbi.md`](docs/powerbi.md). CSVs are pre-exported to `dashboard/powerbi_exports/`.

## Business Insights

Derived from the actual generated data (not invented afterward) — see the live output of `python -m src.risk_engine.unified_risk` and `data/processed/recommendations.json`, e.g.:
- Two suppliers showed a real, detectable lead-time/OTIF collapse in Jul–Sep 2024, correctly flagged as high/critical risk by the model.
- 139 SKU-warehouse combinations are currently in High/Critical stockout-risk bands.
- The largest inventory inefficiencies cluster in specific SKU-warehouse pairs carrying 15+ days of supply above the network median.

## Business Impact

**Estimated / simulated** (clearly labeled, methodology documented in [`src/risk_engine/business_impact.py`](src/risk_engine/business_impact.py)) on this run:
- Estimated annual lost margin from stockouts: **₹79.1M**
- Estimated annual holding cost on excess inventory: **₹31.1M**
- Estimated annual expedited-shipping premium: **₹128.2M**
- **Total estimated annual risk exposure: ₹238.4M** | Estimated recoverable opportunity (40% addressable via recommendations): **₹95.3M**

These are illustrative figures computed on synthetic data using documented assumptions — they demonstrate the *method*, not real company results.

## Project Structure

```
SupplyIQ/
├── config/                  # Central config (paths, seeds, business constants)
├── data/{raw,processed,synthetic}/
├── database/{schema,seeds,queries}/
├── sql/{staging,warehouse,marts,analytics}/
├── src/
│   ├── data_generation/     # Simulated dimension + fact table generation
│   ├── ingestion/           # Raw -> staging loading
│   ├── validation/          # Data quality engine
│   ├── preprocessing/       # Cleaning -> trusted warehouse
│   ├── features/            # Time-safe feature panels
│   ├── forecasting/         # Demand forecasting
│   ├── models/              # Stockout risk, supplier risk
│   ├── anomaly_detection/   # Isolation Forest + z-score
│   ├── risk_engine/         # Unified risk + root cause + business impact
│   ├── recommendations/     # Decision/recommendation engine
│   ├── llm/                 # Grounded GenAI analyst
│   ├── api/                 # FastAPI app
│   └── utils/                # Logging etc.
├── app/                     # Streamlit application
├── dashboard/powerbi_exports/
├── tests/                   # pytest suite (34 tests)
├── scripts/                 # Orchestrator + PowerShell setup scripts
└── docs/                    # Architecture, data dictionary, ML methodology, etc.
```

## Installation

```powershell
git clone <your-repo-url>
cd SupplyIQ
.\scripts\setup.ps1
```

This creates a venv, installs `requirements.txt` (verified to install cleanly in a fresh environment), and creates `.env` from `.env.example`.

**Manual equivalent** (if you prefer not to use the script):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

## Database Setup

No separate database server is required — SQLite is created automatically by the pipeline at `database/supplyiq.db`. If you want a real Postgres instance instead, see `database/schema/schema_postgres.sql` and the notes in [`docs/deployment.md`](docs/deployment.md).

## Configuration

Edit `.env` (see `.env.example`). Everything works with the defaults — the only optional setting is enabling an LLM provider for the AI Analyst (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`).

## Running Locally

```powershell
.\scripts\run_pipeline.ps1        # generates data, builds DB, trains models, runs tests (~2 minutes)
.\scripts\start_app.ps1           # starts API (localhost:8000) + Streamlit (localhost:8501)
```

Or run the pieces individually — see [`docs/deployment.md`](docs/deployment.md) for every command.

## Docker

```bash
docker compose up --build
```
Runs the pipeline once, then starts the API (`:8000`) and Streamlit app (`:8501`). **Note:** the Docker build/run was authored and reviewed for correctness but could not be executed inside the sandboxed environment used to build this project (no Docker daemon available there) — see the Limitations section below.

## Testing

```powershell
pytest tests/ -v
```
34 tests covering data generation integrity, data-quality scoring, cleaning rules, risk-scoring boundaries, recommendation logic, and all API endpoints. **All 34 pass** on the reference run (see `scripts/run_pipeline.py` output).

## Screenshots

Not included as static images in this repo (the app is fully runnable — `streamlit run app/Home.py` — so screenshots would just go stale). Take your own after running the pipeline; suggested shots: Executive Command Center KPIs, Supplier Risk explainability view, AI Analyst chat.

## Example AI Questions

- "Why is supplier risk increasing?"
- "Which SKUs are most likely to stock out?"
- "What are the biggest inventory inefficiencies?"
- "What action should operations take this week?"
- "What is the estimated financial impact of current risks?"

## Limitations

- **Synthetic data**: realistic and internally coherent, but not real transactional data — models and impact figures illustrate methodology, not real business results.
- **Stockout risk model** has moderate discriminative power (ROC-AUC 0.67) — genuine demand spikes are partly stochastic by design and not fully predictable a week ahead; this is reported honestly rather than hidden.
- **Docker & a live Postgres deployment were not executed** in the build environment (no Docker daemon / Postgres server available there) — the Dockerfile, compose file, and Postgres schema are provided and reviewed but should be validated on your machine.
- **Power BI `.pbix` file** cannot be authored by a script (Windows-only, binary format) — a complete, exact-steps guide and pre-exported data are provided instead.
- The GenAI layer's LLM-backed mode was tested only in local-fallback mode during the build (no API key was used) — the LLM request code path is implemented per the Anthropic/OpenAI API spec but wasn't exercised against a live key.

## Future Improvements

- Swap SQLite for Postgres/Snowflake with the provided schema for true concurrent multi-user access.
- Add SHAP-based per-prediction explanations (currently: global feature importances + transparent rule-based drivers).
- Extend the forecasting model to a hierarchical (SKU → category → total) reconciliation approach.
- Add a scheduled retraining job (e.g., Airflow/Prefect) instead of on-demand pipeline runs.
- Wire the recommendation engine's "expected benefit" into a feedback loop that tracks whether recommended actions were taken and what actually happened.

## Author

Built as a portfolio project demonstrating end-to-end data science, data engineering, analytics engineering, and AI/ML capability for Data Analyst / BI Analyst / Data Scientist / Analytics Engineer roles.
