-- =============================================================================
-- SupplyIQ — Data Warehouse Schema (SQLite dialect)
-- =============================================================================
-- Star schema: one fact table per business process, surrounded by shared
-- conformed dimensions. A Postgres-compatible version of this same schema
-- lives in database/schema/schema_postgres.sql (SERIAL instead of
-- AUTOINCREMENT, plus native indexes/partitioning notes) for teams that want
-- a "real" client-server database instead of the zero-setup SQLite file used
-- by default in this project.
--
-- WHY SQLite by default: this is a portfolio project meant to run on a bare
-- Windows machine in minutes with no server to install. The schema, SQL, and
-- star-schema design are identical in spirit to what you'd run on Postgres/
-- Snowflake in production — only the DDL dialect and a couple of index
-- features differ. See docs/architecture.md for the tradeoff discussion.
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- DIMENSIONS
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS dim_date;
CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,
    date            TEXT NOT NULL,
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT NOT NULL,
    week_of_year    INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,
    day_name        TEXT NOT NULL,
    is_weekend      INTEGER NOT NULL,
    is_peak_season  INTEGER NOT NULL,
    fiscal_year     INTEGER NOT NULL
);

DROP TABLE IF EXISTS dim_region;
CREATE TABLE dim_region (
    region_id             INTEGER PRIMARY KEY,
    region_name           TEXT NOT NULL,
    demand_index          REAL NOT NULL,
    logistics_cost_index  REAL NOT NULL
);

DROP TABLE IF EXISTS dim_warehouse;
CREATE TABLE dim_warehouse (
    warehouse_id      INTEGER PRIMARY KEY,
    warehouse_code    TEXT UNIQUE NOT NULL,
    warehouse_name    TEXT NOT NULL,
    region_id         INTEGER NOT NULL REFERENCES dim_region(region_id),
    capacity_units    INTEGER NOT NULL,
    automation_level  TEXT NOT NULL,
    opened_year       INTEGER NOT NULL
);

DROP TABLE IF EXISTS dim_product;
CREATE TABLE dim_product (
    product_id        INTEGER PRIMARY KEY,
    sku               TEXT UNIQUE NOT NULL,
    product_name      TEXT NOT NULL,
    category          TEXT NOT NULL,
    unit_cost         REAL NOT NULL,
    unit_price        REAL NOT NULL,
    base_daily_demand REAL NOT NULL,
    is_seasonal       INTEGER NOT NULL,
    shelf_life_days   INTEGER NOT NULL,
    abc_class_hint    TEXT
);

DROP TABLE IF EXISTS dim_supplier;
CREATE TABLE dim_supplier (
    supplier_id           INTEGER PRIMARY KEY,
    supplier_code         TEXT UNIQUE NOT NULL,
    supplier_name         TEXT NOT NULL,
    country               TEXT NOT NULL,
    archetype             TEXT NOT NULL,
    base_otif_rate        REAL NOT NULL,
    base_lead_time_days   REAL NOT NULL,
    lead_time_volatility  REAL NOT NULL,
    defect_rate           REAL NOT NULL,
    cost_volatility       REAL NOT NULL,
    onboarded_year        INTEGER NOT NULL,
    is_single_source      INTEGER NOT NULL
);

DROP TABLE IF EXISTS dim_customer_segment;
CREATE TABLE dim_customer_segment (
    customer_segment_id     INTEGER PRIMARY KEY,
    segment_name            TEXT NOT NULL,
    avg_order_value_index   REAL NOT NULL,
    price_sensitivity       REAL NOT NULL
);

DROP TABLE IF EXISTS dim_transport_mode;
CREATE TABLE dim_transport_mode (
    transport_mode_id          INTEGER PRIMARY KEY,
    mode_name                  TEXT NOT NULL,
    typical_transit_days_min   INTEGER NOT NULL,
    typical_transit_days_max   INTEGER NOT NULL,
    relative_cost_index        REAL NOT NULL
);

DROP TABLE IF EXISTS bridge_supplier_product;
CREATE TABLE bridge_supplier_product (
    link_id               INTEGER PRIMARY KEY,
    supplier_id           INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    product_id            INTEGER NOT NULL REFERENCES dim_product(product_id),
    warehouse_id          INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    negotiated_unit_cost  REAL NOT NULL,
    is_primary_supplier   INTEGER NOT NULL,
    moq_units             INTEGER NOT NULL
);

-- -----------------------------------------------------------------------------
-- FACTS
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS fact_orders;
CREATE TABLE fact_orders (
    order_id                INTEGER,
    order_date              TEXT NOT NULL,
    product_id              INTEGER NOT NULL REFERENCES dim_product(product_id),
    warehouse_id            INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    region_id               INTEGER NOT NULL REFERENCES dim_region(region_id),
    customer_segment_id     INTEGER NOT NULL REFERENCES dim_customer_segment(customer_segment_id),
    supplier_id             INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    transport_mode_id       REAL,
    order_qty               INTEGER NOT NULL,
    unit_price               REAL,
    revenue                 REAL,
    order_status             TEXT,
    promised_delivery_date  TEXT,
    actual_delivery_date    TEXT,
    is_late                 INTEGER
);

DROP TABLE IF EXISTS fact_shipments;
CREATE TABLE fact_shipments (
    shipment_id             INTEGER PRIMARY KEY,
    warehouse_id            INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    supplier_id             INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    transport_mode_id       INTEGER NOT NULL REFERENCES dim_transport_mode(transport_mode_id),
    ship_date               TEXT NOT NULL,
    promised_delivery_date  TEXT NOT NULL,
    actual_delivery_date    TEXT NOT NULL,
    n_orders                INTEGER NOT NULL,
    total_qty               REAL NOT NULL,
    distance_km             REAL NOT NULL,
    shipping_cost           REAL NOT NULL,
    is_otif                 INTEGER NOT NULL
);

DROP TABLE IF EXISTS fact_inventory_snapshot;
CREATE TABLE fact_inventory_snapshot (
    snapshot_id         INTEGER PRIMARY KEY,
    snapshot_date       TEXT NOT NULL,
    product_id          INTEGER NOT NULL REFERENCES dim_product(product_id),
    warehouse_id        INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    inventory_on_hand   REAL NOT NULL,
    reorder_point       REAL NOT NULL,
    days_of_supply      REAL NOT NULL,
    week_demand         REAL NOT NULL
);

DROP TABLE IF EXISTS fact_supplier_performance;
CREATE TABLE fact_supplier_performance (
    supplier_id             INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    performance_month       TEXT NOT NULL,
    order_count             INTEGER NOT NULL,
    on_time_count           INTEGER NOT NULL,
    fulfilled_count         INTEGER NOT NULL,
    avg_qty                 REAL NOT NULL,
    total_revenue           REAL NOT NULL,
    otif_rate               REAL NOT NULL,
    fill_rate               REAL NOT NULL,
    supplier_name            TEXT NOT NULL,
    avg_lead_time_days      REAL NOT NULL,
    defect_rate_observed    REAL NOT NULL,
    cost_variance_pct       REAL NOT NULL,
    PRIMARY KEY (supplier_id, performance_month)
);

-- -----------------------------------------------------------------------------
-- INDEXES (query-pattern driven — see docs/architecture.md for rationale)
-- -----------------------------------------------------------------------------
CREATE INDEX idx_orders_date ON fact_orders(order_date);
CREATE INDEX idx_orders_product ON fact_orders(product_id);
CREATE INDEX idx_orders_warehouse ON fact_orders(warehouse_id);
CREATE INDEX idx_orders_supplier ON fact_orders(supplier_id);
CREATE INDEX idx_orders_status ON fact_orders(order_status);

CREATE INDEX idx_shipments_supplier ON fact_shipments(supplier_id);
CREATE INDEX idx_shipments_date ON fact_shipments(ship_date);

CREATE INDEX idx_inventory_product_wh ON fact_inventory_snapshot(product_id, warehouse_id);
CREATE INDEX idx_inventory_date ON fact_inventory_snapshot(snapshot_date);

CREATE INDEX idx_supplierperf_month ON fact_supplier_performance(performance_month);
