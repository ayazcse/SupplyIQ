# Deployment

## Option A — Local (no Docker), Windows PowerShell

```powershell
.\scripts\setup.ps1          # venv + dependencies + .env
.\scripts\run_pipeline.ps1   # generate data, build DB, train models, run tests (~2 min)
.\scripts\start_app.ps1      # starts API (:8000) + Streamlit (:8501) in separate windows
```

Individual commands (if you want to run stages one at a time):
```powershell
.\venv\Scripts\Activate.ps1
python -m src.data_generation.generate_dimensions
python -m src.data_generation.generate_facts
python -m src.ingestion.load_raw
python -m src.validation.data_quality
python -m src.preprocessing.clean_orders
python scripts\run_sql_queries.py
python -m src.features.build_features
python -m src.forecasting.demand_forecast
python -m src.models.stockout_risk_model
python -m src.models.supplier_risk_model
python -m src.anomaly_detection.detect_anomalies
python -m src.risk_engine.unified_risk
python -m src.risk_engine.business_impact
python -m src.recommendations.recommendation_engine
python scripts\flatten_json_for_powerbi.py
pytest tests\ -v

uvicorn src.api.main:app --reload --port 8000
streamlit run app\Home.py
```

## Option B — Docker

```bash
docker compose up --build
```

This builds one image and runs three services: `pipeline` (runs once and
exits after generating data/training models), then `api` (:8000) and `app`
(:8501), both waiting for `pipeline` to complete successfully first.

**Status: written and reviewed, not executed.** The environment used to
build this project had no Docker daemon available, so the Dockerfile and
compose file could not be run end-to-end here. Before relying on this in
an interview, run `docker compose up --build` yourself and fix anything
that comes up — the most likely rough edges are: (1) `libgomp1` being the
right system package for LightGBM on `python:3.12-slim` (it is, per
LightGBM's own documentation, but wasn't verified in this build), and
(2) file permission issues if the `data/` and `database/` bind mounts are
owned by a different user inside vs. outside the container on your OS.

## Option C — Swap in PostgreSQL instead of SQLite

1. Start a Postgres instance (locally or via `docker run postgres:16`).
2. Apply the schema: `psql -U postgres -d supplyiq -f database/schema/schema_postgres.sql`
3. In `src/ingestion/load_raw.py`, replace the `sqlite3.connect()` calls
   with a SQLAlchemy engine: `create_engine("postgresql://user:pass@localhost/supplyiq")`.
   `pandas.read_sql` / `DataFrame.to_sql` both accept a SQLAlchemy engine
   directly, so the rest of the codebase (`src/models`, `src/risk_engine`,
   `src/api`, `app/`) needs no changes beyond this one connection factory.
4. Update `.env`: point `SQLITE_DB_PATH` usage aside and add a
   `DATABASE_URL` variable if you want it configurable (not currently
   wired in, since the project defaults to SQLite — see
   `docs/architecture.md` for why).

**Status: schema written and reviewed, not executed against a live
Postgres instance** in this build (no Postgres server available in the
build sandbox).

## Environment variables

See `.env.example`. Nothing is required for the core pipeline, API, or app
to run — the only optional variables (`LLM_PROVIDER`, `LLM_MODEL`,
`LLM_API_KEY`) enable natural-language synthesis in the AI Analyst; without
them it runs in a fully functional local template mode.
