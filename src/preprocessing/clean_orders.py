"""
Preprocessing / Cleaning layer.

Takes the raw `staging_fact_orders_raw` table (TEXT columns, deliberately
messy) and produces a cleaned, typed DataFrame that is loaded into the
warehouse `fact_orders` table used by all downstream SQL, analytics, and ML.

Cleaning rules applied (each documented + logged with an affected-row count,
so the transformation is auditable rather than silent):
1. Drop exact duplicate order_id rows, keeping the first occurrence.
2. Normalize order_status to canonical Title Case labels.
3. Fix negative unit_price via absolute value (documented assumption: sign
   error at entry, not a real credit/refund -- a real pipeline would confirm
   with the source system).
4. Impute missing unit_price with that product's catalog price.
5. Impute missing transport_mode_id with the warehouse's most common mode.
6. Flag (not silently drop) extreme quantity outliers via an `is_outlier_qty`
   column, so analysts can choose to exclude them without losing the record.
7. Cast all IDs/dates/numerics to proper types.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np
import pandas as pd

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.utils.logger import get_logger

log = get_logger(__name__)

STATUS_MAP = {
    "fulfilled": "Fulfilled", "stockout": "Stockout", "partial": "Partial",
}


def clean_orders(raw: pd.DataFrame, dim_product: pd.DataFrame, dim_warehouse_mode: dict) -> pd.DataFrame:
    df = raw.copy()
    before = len(df)

    # 1. Dedup
    df = df.drop_duplicates(subset=["order_id"], keep="first")
    log.info(f"Dropped {before - len(df):,} duplicate order_id rows.")

    # Type casts
    for col in ["order_id", "product_id", "warehouse_id", "region_id",
                "customer_segment_id", "supplier_id"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["transport_mode_id"] = pd.to_numeric(df["transport_mode_id"], errors="coerce")
    df["order_qty"] = pd.to_numeric(df["order_qty"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce")
    df["is_late"] = df["is_late"].map({"True": True, "False": False}).astype("boolean")
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["promised_delivery_date"] = pd.to_datetime(df["promised_delivery_date"], errors="coerce")
    df["actual_delivery_date"] = pd.to_datetime(df["actual_delivery_date"], errors="coerce")

    # 2. Normalize status
    norm = df["order_status"].astype(str).str.strip().str.lower()
    n_fixed = (~df["order_status"].isin(STATUS_MAP.values())).sum()
    df["order_status"] = norm.map(STATUS_MAP).fillna(df["order_status"])
    log.info(f"Normalized {n_fixed:,} inconsistent order_status labels.")

    # 3. Fix negative prices
    n_neg = (df["unit_price"] < 0).sum()
    df["unit_price"] = df["unit_price"].abs()
    log.info(f"Corrected sign on {n_neg:,} negative unit_price values.")

    # 4. Impute missing prices from product catalog
    price_map = dim_product.set_index("product_id")["unit_price"].to_dict()
    n_missing_price = df["unit_price"].isna().sum()
    fallback_price = df["product_id"].map(price_map)
    df["unit_price"] = df["unit_price"].fillna(fallback_price)
    df["revenue"] = df["revenue"].fillna(df["unit_price"] * df["order_qty"])
    log.info(f"Imputed {n_missing_price:,} missing unit_price values from product catalog.")

    # 5. Impute missing transport mode with warehouse's most common mode
    n_missing_mode = df["transport_mode_id"].isna().sum()
    df["transport_mode_id"] = df.apply(
        lambda r: dim_warehouse_mode.get(r["warehouse_id"], 1) if pd.isna(r["transport_mode_id"]) else r["transport_mode_id"],
        axis=1,
    )
    log.info(f"Imputed {n_missing_mode:,} missing transport_mode_id values.")

    # 6. Flag extreme outliers instead of dropping (preserve information)
    q1, q3 = df["order_qty"].quantile([0.25, 0.75])
    iqr = q3 - q1
    upper = q3 + 3 * iqr
    df["is_outlier_qty"] = df["order_qty"] > upper
    log.info(f"Flagged {df['is_outlier_qty'].sum():,} rows as extreme quantity outliers (kept, not dropped).")

    df["is_late"] = df["is_late"].fillna(False)
    df["transport_mode_id"] = df["transport_mode_id"].astype(float)
    df["order_qty"] = df["order_qty"].astype("Int64")

    return df


def main():
    conn = get_connection()
    raw = pd.read_sql("SELECT * FROM staging_fact_orders_raw", conn)
    dim_product = pd.read_sql("SELECT product_id, unit_price FROM dim_product", conn)

    # Warehouse's most common transport mode, derived from the data itself
    modes = pd.read_sql("""
        SELECT warehouse_id, transport_mode_id, COUNT(*) as cnt
        FROM staging_fact_orders_raw
        WHERE transport_mode_id IS NOT NULL AND transport_mode_id != ''
        GROUP BY warehouse_id, transport_mode_id
    """, conn)
    modes["warehouse_id"] = pd.to_numeric(modes["warehouse_id"])
    modes["transport_mode_id"] = pd.to_numeric(modes["transport_mode_id"])
    dim_warehouse_mode = modes.sort_values("cnt", ascending=False).drop_duplicates("warehouse_id").set_index("warehouse_id")["transport_mode_id"].to_dict()

    log.info(f"Cleaning {len(raw):,} raw order rows...")
    cleaned = clean_orders(raw, dim_product, dim_warehouse_mode)

    # Add an is_outlier_qty column to the warehouse schema if not present
    try:
        conn.execute("ALTER TABLE fact_orders ADD COLUMN is_outlier_qty INTEGER")
        conn.commit()
    except Exception:
        pass  # column already exists (safe to re-run this script)

    conn.execute("DELETE FROM fact_orders")
    cleaned_for_sql = cleaned.copy()
    for c in ["order_date", "promised_delivery_date", "actual_delivery_date"]:
        cleaned_for_sql[c] = cleaned_for_sql[c].dt.strftime("%Y-%m-%d")
    cleaned_for_sql.to_sql("fact_orders", conn, if_exists="append", index=False)
    conn.commit()
    conn.close()

    cleaned.to_csv(cfg.PROCESSED_DIR / "fact_orders_clean.csv", index=False)

    log.info(f"Loaded {len(cleaned):,} cleaned rows into warehouse fact_orders table.")
    log.info("Preprocessing complete.")


if __name__ == "__main__":
    main()
