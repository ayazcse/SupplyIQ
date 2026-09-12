"""
Ingestion layer: loads the synthetic CSV extracts into SQLite.

- Dimension tables and already-clean fact tables (shipments, inventory,
  supplier performance) are loaded directly into the warehouse schema.
- fact_orders (which has deliberately injected data-quality issues) is loaded
  into a TEXT-typed STAGING table first, so nothing fails on dirty data. It is
  only promoted into the warehouse's typed fact_orders table after
  src/preprocessing/clean_orders.py has run.

This mirrors a real ELT pattern: land raw data untouched, validate it, then
transform into the trusted layer.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd

from config import config as cfg
from src.utils.logger import get_logger

log = get_logger(__name__)

CLEAN_LOAD_ORDER = [
    ("dim_date.csv", "dim_date"),
    ("dim_region.csv", "dim_region"),
    ("dim_warehouse.csv", "dim_warehouse"),
    ("dim_product.csv", "dim_product"),
    ("dim_supplier.csv", "dim_supplier"),
    ("dim_customer_segment.csv", "dim_customer_segment"),
    ("dim_transport_mode.csv", "dim_transport_mode"),
    ("bridge_supplier_product.csv", "bridge_supplier_product"),
    ("fact_shipments.csv", "fact_shipments"),
    ("fact_inventory_snapshot.csv", "fact_inventory_snapshot"),
    ("fact_supplier_performance.csv", "fact_supplier_performance"),
]


def get_connection() -> sqlite3.Connection:
    cfg.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(cfg.DB_PATH)


def build_schema(conn: sqlite3.Connection):
    schema_dir = cfg.ROOT_DIR / "database" / "schema"
    for fname in ["schema_sqlite.sql", "schema_staging.sql"]:
        sql_text = (schema_dir / fname).read_text()
        conn.executescript(sql_text)
    conn.commit()
    log.info("Schema (warehouse + staging) created.")


def build_views(conn: sqlite3.Connection):
    """Warehouse-layer views and executive mart -- see sql/warehouse/ and
    sql/marts/. Run after load_clean_tables/load_staging_orders since some
    views join across dimension and fact tables that must already be loaded
    for SQLite to validate the view definitions... actually SQLite doesn't
    validate view bodies at CREATE time, but running this after data load
    keeps behavior consistent with databases (like Postgres) that do."""
    sql_dir = cfg.ROOT_DIR / "sql"
    for rel_path in ["warehouse/create_warehouse_views.sql", "marts/mart_executive_summary.sql"]:
        conn.executescript((sql_dir / rel_path).read_text())
    conn.commit()
    log.info("Warehouse views and executive mart created.")


def load_clean_tables(conn: sqlite3.Connection):
    for csv_name, table_name in CLEAN_LOAD_ORDER:
        path = cfg.SYNTHETIC_DIR / csv_name
        df = pd.read_csv(path)
        df.to_sql(table_name, conn, if_exists="append", index=False)
        log.info(f"Loaded {len(df):,} rows -> {table_name}")


def load_staging_orders(conn: sqlite3.Connection):
    path = cfg.SYNTHETIC_DIR / "fact_orders.csv"
    df = pd.read_csv(path, dtype=str)  # keep everything as text -- this IS the raw landing zone
    df.to_sql("staging_fact_orders_raw", conn, if_exists="append", index=False)
    log.info(f"Loaded {len(df):,} raw rows -> staging_fact_orders_raw")


def main():
    log.info(f"Building database at {cfg.DB_PATH}")
    conn = get_connection()
    try:
        build_schema(conn)
        load_clean_tables(conn)
        load_staging_orders(conn)
        build_views(conn)
        conn.commit()
        log.info("Ingestion complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
