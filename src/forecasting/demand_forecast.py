"""
Demand Forecasting
===================
Predicts next-week demand per (product, warehouse) and compares two
approaches, using PROPER time-based validation (train on earlier weeks,
test on later weeks -- never a random shuffle split, which would leak
future information into training for time-series data):

1. Seasonal-naive baseline: predict this week's demand = same product's
   4-week rolling average (a legitimate, commonly used forecasting
   baseline -- not a strawman).
2. LightGBM gradient-boosted regression using lag/rolling/calendar features.

Metrics: MAE, RMSE, MAPE, WAPE (WAPE is more robust than MAPE when many
actuals are small/zero, which is common in SKU-level demand data).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)

FEATURES = [
    "demand_lag_1", "demand_lag_2", "demand_roll4_mean", "demand_roll4_std",
    "demand_roll8_mean", "demand_pct_change", "inventory_on_hand", "days_of_supply",
    "base_lead_time_days", "lead_time_volatility", "base_otif_rate", "defect_rate",
    "is_seasonal", "week_of_year", "month", "order_count",
]
TARGET = "target_demand_next_week"


def compute_metrics(y_true, y_pred, label: str) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    nonzero = y_true != 0
    mape = np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero])) * 100 if nonzero.any() else np.nan
    wape = np.sum(np.abs(y_true - y_pred)) / np.sum(np.abs(y_true)) * 100 if np.sum(np.abs(y_true)) > 0 else np.nan
    metrics = {"model": label, "MAE": round(mae, 2), "RMSE": round(rmse, 2),
               "MAPE_%": round(mape, 2), "WAPE_%": round(wape, 2)}
    log.info(f"{label:20s} | MAE={mae:8.2f}  RMSE={rmse:8.2f}  MAPE={mape:6.2f}%  WAPE={wape:6.2f}%")
    return metrics


def main():
    df = pd.read_csv(cfg.PROCESSED_DIR / "weekly_panel.csv", parse_dates=["week"])
    df = df.dropna(subset=[TARGET]).copy()
    df["is_seasonal"] = df["is_seasonal"].astype(int)

    # Time-based split: last 15% of calendar weeks = test set. This is the
    # correct way to validate time series -- never a random row-level split.
    cutoff = df["week"].quantile(0.85)
    train = df[df["week"] <= cutoff].dropna(subset=FEATURES)
    test = df[df["week"] > cutoff].dropna(subset=FEATURES)
    log.info(f"Train: {len(train):,} rows (up to {cutoff.date()}) | Test: {len(test):,} rows (after)")

    # --- Baseline: seasonal-naive (4-week rolling average IS the forecast) ---
    baseline_pred = test["demand_roll4_mean"].fillna(test["demand_lag_1"])
    baseline_metrics = compute_metrics(test[TARGET], baseline_pred, "Baseline (roll-4-avg)")

    # --- LightGBM gradient boosting ---
    model = LGBMRegressor(
        n_estimators=300, learning_rate=0.05, num_leaves=31,
        min_child_samples=20, random_state=cfg.RANDOM_SEED, verbosity=-1,
    )
    model.fit(train[FEATURES], train[TARGET])
    gbm_pred = np.maximum(0, model.predict(test[FEATURES]))
    gbm_metrics = compute_metrics(test[TARGET], gbm_pred, "LightGBM")

    # Save model + comparison + feature importance
    import joblib
    cfg.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, cfg.MODELS_DIR / "demand_forecast_lgbm.joblib")

    comparison = pd.DataFrame([baseline_metrics, gbm_metrics])
    comparison.to_csv(cfg.PROCESSED_DIR / "forecast_model_comparison.csv", index=False)

    importance = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importances_}).sort_values(
        "importance", ascending=False)
    importance.to_csv(cfg.PROCESSED_DIR / "forecast_feature_importance.csv", index=False)

    # Save actual-vs-predicted sample for the app/report to plot
    out = test[["product_id", "warehouse_id", "week", TARGET]].copy()
    out["predicted_demand"] = gbm_pred
    out["baseline_predicted_demand"] = baseline_pred.values
    out.to_csv(cfg.PROCESSED_DIR / "forecast_actual_vs_predicted.csv", index=False)

    with open(cfg.PROCESSED_DIR / "forecast_model_card.json", "w") as f:
        json.dump({
            "objective": "Predict next-week order demand (units) per product-warehouse pair",
            "target": TARGET,
            "features": FEATURES,
            "train_rows": len(train), "test_rows": len(test),
            "validation_strategy": "Time-based split (train <= 85th percentile week, test after) -- no random shuffling",
            "models_compared": ["Seasonal-naive (4-week rolling average)", "LightGBM gradient boosting"],
            "metrics": {"baseline": baseline_metrics, "lightgbm": gbm_metrics},
            "chosen_model": "LightGBM" if gbm_metrics["WAPE_%"] < baseline_metrics["WAPE_%"] else "Baseline",
            "limitations": [
                "Trained on 3 years of simulated data; real deployments should retrain periodically as seasonality drifts.",
                "Cold-start products (no order history) fall back to the baseline in the app layer.",
                "Demand surge/shock events are learnable in-sample but a genuinely novel shock will still cause forecast error.",
            ],
        }, f, indent=2)

    log.info("Forecasting complete. Model + metrics + model card saved.")
    print("\nMODEL COMPARISON:\n", comparison.to_string(index=False))


if __name__ == "__main__":
    main()
