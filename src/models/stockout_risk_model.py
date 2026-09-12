"""
Stockout Risk Model
=====================
Binary classifier predicting P(stockout in the NEXT week) per
(product, warehouse), using only features known as-of the current week
(lags, rolling stats, current inventory position, supplier reliability).

Output: stockout_probability (0-1) -> mapped to Low/Medium/High/Critical
bands (see config.STOCKOUT_RISK_BANDS).

Validation: time-based split (same rationale as forecasting -- a random
split would let the model "see the future" via correlated nearby weeks).
Class imbalance (stockouts are a minority class) is handled via
class_weight='balanced' rather than naive oversampling, and evaluated with
precision/recall/F1/ROC-AUC/PR-AUC rather than accuracy (which would be
misleadingly high on an imbalanced target).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import (roc_auc_score, average_precision_score, precision_score,
                              recall_score, f1_score, confusion_matrix)

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)

FEATURES = [
    "demand_lag_1", "demand_lag_2", "demand_roll4_mean", "demand_roll4_std",
    "demand_roll8_mean", "demand_pct_change", "inventory_on_hand", "days_of_supply",
    "base_lead_time_days", "lead_time_volatility", "base_otif_rate", "defect_rate",
    "is_seasonal", "week_of_year", "month", "order_count", "late_orders",
]
TARGET = "target_stockout_next_week"


def band_from_prob(p: float) -> str:
    for lo, hi, label in cfg.STOCKOUT_RISK_BANDS:
        if lo <= p < hi:
            return label
    return "Critical"


def main():
    df = pd.read_csv(cfg.PROCESSED_DIR / "weekly_panel.csv", parse_dates=["week"])
    df = df.dropna(subset=[TARGET]).copy()
    df["is_seasonal"] = df["is_seasonal"].astype(int)
    df[TARGET] = df[TARGET].astype(int)

    cutoff = df["week"].quantile(0.85)
    train = df[df["week"] <= cutoff].dropna(subset=FEATURES)
    test = df[df["week"] > cutoff].dropna(subset=FEATURES)
    log.info(f"Train: {len(train):,} rows | Test: {len(test):,} rows | "
              f"Train stockout rate: {train[TARGET].mean():.3f} | Test stockout rate: {test[TARGET].mean():.3f}")

    model = LGBMClassifier(
        n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=20,
        class_weight="balanced", random_state=cfg.RANDOM_SEED, verbosity=-1,
    )
    model.fit(train[FEATURES], train[TARGET])

    proba = model.predict_proba(test[FEATURES])[:, 1]
    preds = (proba >= 0.5).astype(int)

    metrics = {
        "roc_auc": round(roc_auc_score(test[TARGET], proba), 4),
        "pr_auc": round(average_precision_score(test[TARGET], proba), 4),
        "precision": round(precision_score(test[TARGET], preds, zero_division=0), 4),
        "recall": round(recall_score(test[TARGET], preds, zero_division=0), 4),
        "f1": round(f1_score(test[TARGET], preds, zero_division=0), 4),
    }
    cm = confusion_matrix(test[TARGET], preds).tolist()
    log.info(f"ROC-AUC={metrics['roc_auc']}  PR-AUC={metrics['pr_auc']}  "
              f"Precision={metrics['precision']}  Recall={metrics['recall']}  F1={metrics['f1']}")
    log.info(f"Confusion matrix [[TN,FP],[FN,TP]]: {cm}")

    import joblib
    cfg.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, cfg.MODELS_DIR / "stockout_risk_lgbm.joblib")

    importance = pd.DataFrame({"feature": FEATURES, "importance": model.feature_importances_}).sort_values(
        "importance", ascending=False)
    importance.to_csv(cfg.PROCESSED_DIR / "stockout_feature_importance.csv", index=False)

    out = test[["product_id", "warehouse_id", "week", TARGET]].copy()
    out["stockout_probability"] = proba
    out["risk_band"] = out["stockout_probability"].apply(band_from_prob)
    out.to_csv(cfg.PROCESSED_DIR / "stockout_risk_predictions.csv", index=False)

    with open(cfg.PROCESSED_DIR / "stockout_model_card.json", "w") as f:
        json.dump({
            "objective": "Predict probability of a stockout occurring next week for a given product-warehouse",
            "target": TARGET,
            "features": FEATURES,
            "train_rows": len(train), "test_rows": len(test),
            "class_balance": {"train_positive_rate": round(float(train[TARGET].mean()), 4),
                               "test_positive_rate": round(float(test[TARGET].mean()), 4)},
            "validation_strategy": "Time-based split; class_weight='balanced' to handle minority-class stockouts",
            "metrics": metrics, "confusion_matrix": cm,
            "risk_bands": cfg.STOCKOUT_RISK_BANDS,
            "limitations": [
                "Stockouts are a minority class even after balancing -- precision/recall tradeoff should be tuned to business risk appetite (recall favored for high-cost stockouts).",
                "Model has not been tested against a genuinely novel supply shock outside the simulated distribution.",
                "Cold-start product-warehouse pairs with <4 weeks history cannot be scored (rolling features are NaN) -- the risk engine falls back to a rule-based score for these.",
            ],
        }, f, indent=2)

    log.info("Stockout risk model complete.")


if __name__ == "__main__":
    main()
