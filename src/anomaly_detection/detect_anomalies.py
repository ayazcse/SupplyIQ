"""
Anomaly Detection
===================
Two complementary, justified methods (not ML for its own sake):

1. Isolation Forest (multivariate) on the weekly product-warehouse panel --
   good for catching *combinations* of features that are jointly unusual
   (e.g., demand up AND inventory down AND lead time up simultaneously) even
   if no single metric crosses an obvious threshold.
2. Rolling Z-score (univariate, per product-warehouse time series) -- good
   for catching a single metric that suddenly deviates from ITS OWN recent
   history, which is more interpretable and works even for products with
   too little history for the multivariate model to trust.

Both are run; results are merged and deduplicated so the final anomaly list
favors metrics an analyst can act on immediately (with the specific
metric + deviation called out), not just an opaque "this row is weird" score.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)

IFOREST_FEATURES = ["demand_qty", "inventory_on_hand", "days_of_supply", "late_orders", "stockout_orders"]


def run_isolation_forest(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.dropna(subset=IFOREST_FEATURES).copy()
    model = IsolationForest(n_estimators=200, contamination=0.03, random_state=cfg.RANDOM_SEED)
    df["anomaly_score_if"] = -model.fit_predict(df[IFOREST_FEATURES])  # 1 = anomaly (flip sign for intuitive "higher=worse")
    df["anomaly_score_if"] = df["anomaly_score_if"].clip(lower=0)
    df["is_anomaly_multivariate"] = (df["anomaly_score_if"] > 0).astype(int)
    return df


def run_rolling_zscore(panel: pd.DataFrame, metric: str, window: int = 8, z_thresh: float = 3.0) -> pd.DataFrame:
    df = panel.sort_values(["product_id", "warehouse_id", "week"]).copy()
    grp = df.groupby(["product_id", "warehouse_id"])[metric]
    roll_mean = grp.transform(lambda s: s.shift(1).rolling(window).mean())
    roll_std = grp.transform(lambda s: s.shift(1).rolling(window).std())
    df[f"{metric}_zscore"] = (df[metric] - roll_mean) / roll_std.replace(0, np.nan)
    df[f"is_anomaly_{metric}"] = (df[f"{metric}_zscore"].abs() > z_thresh).astype(int)
    return df[[f"{metric}_zscore", f"is_anomaly_{metric}"]]


def main():
    panel = pd.read_csv(cfg.PROCESSED_DIR / "weekly_panel.csv", parse_dates=["week"])

    log.info("Running Isolation Forest (multivariate anomaly detection)...")
    result = run_isolation_forest(panel)

    log.info("Running rolling Z-score (univariate) checks on demand and late_orders...")
    demand_z = run_rolling_zscore(panel, "demand_qty")
    late_z = run_rolling_zscore(panel, "late_orders")
    result = result.join(demand_z).join(late_z)

    result["is_anomaly_any"] = (
        result["is_anomaly_multivariate"].fillna(0).astype(int) |
        result["is_anomaly_demand_qty"].fillna(0).astype(int) |
        result["is_anomaly_late_orders"].fillna(0).astype(int)
    )

    def explain(row):
        reasons = []
        if row.get("is_anomaly_demand_qty", 0) == 1:
            reasons.append(f"demand z-score={row['demand_qty_zscore']:.1f} (vs trailing 8-week pattern)")
        if row.get("is_anomaly_late_orders", 0) == 1:
            reasons.append(f"late-order z-score={row['late_orders_zscore']:.1f}")
        if row.get("is_anomaly_multivariate", 0) == 1:
            reasons.append("flagged by multivariate Isolation Forest (unusual combination of demand/inventory/lead-time)")
        return "; ".join(reasons) if reasons else ""

    result["anomaly_reason"] = result.apply(explain, axis=1)

    anomalies = result[result["is_anomaly_any"] == 1].copy()
    out_cols = ["product_id", "warehouse_id", "week", "demand_qty", "inventory_on_hand",
                "days_of_supply", "late_orders", "stockout_orders", "anomaly_reason"]
    anomalies[out_cols].sort_values("week").to_csv(cfg.PROCESSED_DIR / "anomalies_detected.csv", index=False)

    log.info(f"Total rows scanned: {len(result):,} | Anomalies flagged: {len(anomalies):,} "
              f"({100*len(anomalies)/len(result):.2f}%)")
    print(anomalies[out_cols].tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
