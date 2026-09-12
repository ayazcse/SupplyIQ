"""
SupplyIQ API
=============
FastAPI backend exposing KPIs, risk scores, forecasts, anomalies, and the
grounded AI analyst. Run with:
    uvicorn src.api.main:app --reload --port 8000
Docs auto-generated at http://localhost:8000/docs
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.llm.ai_analyst import ask as ai_ask

app = FastAPI(
    title="SupplyIQ API",
    description="AI-Powered Supply Chain Risk & Decision Intelligence Platform",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _load_json(name: str):
    path = cfg.PROCESSED_DIR / name
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{name} not found -- run scripts/run_pipeline.py first.")
    return json.loads(path.read_text())


class AskRequest(BaseModel):
    question: str


class AnalyzeRequest(BaseModel):
    entity_type: str  # "sku" | "supplier"
    entity_id: str


@app.get("/health")
def health():
    db_ok = cfg.DB_PATH.exists()
    artifacts_ok = (cfg.PROCESSED_DIR / "recommendations.json").exists()
    return {"status": "ok" if (db_ok and artifacts_ok) else "degraded",
            "database_present": db_ok, "analytics_artifacts_present": artifacts_ok}


@app.get("/kpis")
def kpis():
    conn = get_connection()
    total_orders = pd.read_sql("SELECT COUNT(*) c FROM fact_orders", conn).c[0]
    otif = pd.read_sql("SELECT AVG(CASE WHEN is_late=0 THEN 1.0 ELSE 0.0 END) v FROM fact_orders", conn).v[0]
    fill_rate = pd.read_sql(
        "SELECT AVG(CASE WHEN LOWER(TRIM(order_status))='fulfilled' THEN 1.0 ELSE 0.0 END) v FROM fact_orders", conn).v[0]
    stockout_rate = pd.read_sql(
        "SELECT AVG(CASE WHEN LOWER(TRIM(order_status))='stockout' THEN 1.0 ELSE 0.0 END) v FROM fact_orders", conn).v[0]
    revenue = pd.read_sql("SELECT SUM(revenue) v FROM fact_orders", conn).v[0]
    avg_lead_time = pd.read_sql("SELECT AVG(avg_lead_time_days) v FROM fact_supplier_performance", conn).v[0]
    conn.close()

    impact_path = cfg.PROCESSED_DIR / "business_impact_summary.json"
    revenue_at_risk = None
    if impact_path.exists():
        revenue_at_risk = json.loads(impact_path.read_text())["total_estimated_annual_risk_exposure"]

    forecast_metrics = {}
    fc_path = cfg.PROCESSED_DIR / "forecast_model_comparison.csv"
    if fc_path.exists():
        fc = pd.read_csv(fc_path)
        gbm_row = fc[fc.model == "LightGBM"]
        if len(gbm_row):
            forecast_metrics = {"forecast_wape_pct": float(gbm_row["WAPE_%"].values[0])}

    return {
        "total_orders": int(total_orders),
        "otif_rate": round(float(otif), 4),
        "fill_rate": round(float(fill_rate), 4),
        "stockout_rate": round(float(stockout_rate), 4),
        "total_revenue_simulated": round(float(revenue), 0),
        "avg_supplier_lead_time_days": round(float(avg_lead_time), 1),
        "estimated_annual_revenue_at_risk": revenue_at_risk,
        **forecast_metrics,
    }


@app.get("/suppliers/risk")
def suppliers_risk(band: str | None = Query(None, description="Filter by risk band: Low/Moderate/High/Critical")):
    data = _load_json("unified_supplier_risk.json")
    if band:
        data = [d for d in data if d["risk_band"].lower() == band.lower()]
    return {"count": len(data), "suppliers": sorted(data, key=lambda r: -r["risk_score"])}


@app.get("/inventory/risk")
def inventory_risk(band: str | None = Query(None)):
    data = _load_json("unified_sku_risk.json")
    if band:
        data = [d for d in data if d["risk_band"].lower() == band.lower()]
    return {"count": len(data), "items": sorted(data, key=lambda r: -r["stockout_probability"])[:200]}


@app.get("/forecast")
def forecast(product_id: int | None = None, warehouse_id: int | None = None):
    path = cfg.PROCESSED_DIR / "forecast_actual_vs_predicted.csv"
    if not path.exists():
        raise HTTPException(status_code=503, detail="Forecast not available -- run the forecasting pipeline first.")
    df = pd.read_csv(path)
    if product_id is not None:
        df = df[df.product_id == product_id]
    if warehouse_id is not None:
        df = df[df.warehouse_id == warehouse_id]
    return {"count": len(df), "rows": df.tail(200).to_dict(orient="records")}


@app.get("/anomalies")
def anomalies(limit: int = 50):
    path = cfg.PROCESSED_DIR / "anomalies_detected.csv"
    if not path.exists():
        raise HTTPException(status_code=503, detail="Anomaly detection not available -- run the pipeline first.")
    df = pd.read_csv(path)
    return {"count": len(df), "rows": df.tail(limit).to_dict(orient="records")}


@app.get("/recommendations")
def recommendations(urgency: str | None = None):
    data = _load_json("recommendations.json")
    if urgency:
        data = [d for d in data if d["urgency"].lower() == urgency.lower()]
    return {"count": len(data), "recommendations": data}


@app.post("/ask")
def ask_endpoint(req: AskRequest):
    return ai_ask(req.question)


@app.post("/analyze")
def analyze_endpoint(req: AnalyzeRequest):
    if req.entity_type.lower() == "sku":
        data = _load_json("unified_sku_risk.json")
        matches = [d for d in data if d["sku"] == req.entity_id]
    elif req.entity_type.lower() == "supplier":
        data = _load_json("unified_supplier_risk.json")
        matches = [d for d in data if d["supplier_name"] == req.entity_id]
    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'sku' or 'supplier'")
    if not matches:
        raise HTTPException(status_code=404, detail=f"No entity found for {req.entity_type}={req.entity_id}")
    return matches[0]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
