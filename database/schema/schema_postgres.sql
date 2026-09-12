-- =============================================================================
-- SupplyIQ — Data Warehouse Schema (PostgreSQL dialect)
-- =============================================================================
-- Same star schema as database/schema/schema_sqlite.sql (the schema this
-- project actually runs against by default). This file is provided for
-- teams that want a real client-server database instead of the zero-setup
-- SQLite file. It is NOT wired into src/ingestion by default -- doing so
-- means swapping sqlite3.connect() for a SQLAlchemy Postgres engine in
-- src/ingestion/load_raw.py (a couple of lines; SQLAlchemy is already a
-- dependency).
--
-- Key differences from the SQLite version:
--   - SERIAL / GENERATED ALWAYS AS IDENTITY instead of INTEGER PRIMARY KEY autoincrement
--   - Native BOOLEAN type instead of INTEGER 0/1
--   - Explicit DATE / TIMESTAMP types
--   - Table partitioning note for fact_orders at production scale (commented)
-- =============================================================================

CREATE TABLE dim_date (
    date_key        INTEGER PRIMARY KEY,
    date            DATE NOT NULL,
    year            SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL,
    month           SMALLINT NOT NULL,
    month_name      TEXT NOT NULL,
    week_of_year    SMALLINT NOT NULL,
    day_of_week     SMALLINT NOT NULL,
    day_name        TEXT NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    is_peak_season  BOOLEAN NOT NULL,
    fiscal_year     SMALLINT NOT NULL
);

CREATE TABLE dim_region (
    region_id             SERIAL PRIMARY KEY,
    region_name           TEXT NOT NULL,
    demand_index          NUMERIC(6,2) NOT NULL,
    logistics_cost_index  NUMERIC(6,2) NOT NULL
);

CREATE TABLE dim_warehouse (
    warehouse_id      SERIAL PRIMARY KEY,
    warehouse_code    TEXT UNIQUE NOT NULL,
    warehouse_name    TEXT NOT NULL,
    region_id         INTEGER NOT NULL REFERENCES dim_region(region_id),
    capacity_units    INTEGER NOT NULL,
    automation_level  TEXT NOT NULL,
    opened_year       SMALLINT NOT NULL
);

CREATE TABLE dim_product (
    product_id        SERIAL PRIMARY KEY,
    sku               TEXT UNIQUE NOT NULL,
    product_name      TEXT NOT NULL,
    category          TEXT NOT NULL,
    unit_cost         NUMERIC(10,2) NOT NULL,
    unit_price        NUMERIC(10,2) NOT NULL,
    base_daily_demand NUMERIC(10,2) NOT NULL,
    is_seasonal       BOOLEAN NOT NULL,
    shelf_life_days   INTEGER NOT NULL,
    abc_class_hint    TEXT
);

CREATE TABLE dim_supplier (
    supplier_id           SERIAL PRIMARY KEY,
    supplier_code         TEXT UNIQUE NOT NULL,
    supplier_name         TEXT NOT NULL,
    country               TEXT NOT NULL,
    archetype             TEXT NOT NULL,
    base_otif_rate        NUMERIC(5,4) NOT NULL,
    base_lead_time_days   NUMERIC(6,2) NOT NULL,
    lead_time_volatility  NUMERIC(6,2) NOT NULL,
    defect_rate           NUMERIC(6,4) NOT NULL,
    cost_volatility       NUMERIC(6,4) NOT NULL,
    onboarded_year        SMALLINT NOT NULL,
    is_single_source      BOOLEAN NOT NULL
);

CREATE TABLE dim_customer_segment (
    customer_segment_id     SERIAL PRIMARY KEY,
    segment_name            TEXT NOT NULL,
    avg_order_value_index   NUMERIC(6,2) NOT NULL,
    price_sensitivity       NUMERIC(6,2) NOT NULL
);

CREATE TABLE dim_transport_mode (
    transport_mode_id          SERIAL PRIMARY KEY,
    mode_name                  TEXT NOT NULL,
    typical_transit_days_min   SMALLINT NOT NULL,
    typical_transit_days_max   SMALLINT NOT NULL,
    relative_cost_index        NUMERIC(6,2) NOT NULL
);

CREATE TABLE bridge_supplier_product (
    link_id               SERIAL PRIMARY KEY,
    supplier_id           INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    product_id            INTEGER NOT NULL REFERENCES dim_product(product_id),
    warehouse_id          INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    negotiated_unit_cost  NUMERIC(10,2) NOT NULL,
    is_primary_supplier   BOOLEAN NOT NULL,
    moq_units             INTEGER NOT NULL
);

-- At production scale, consider: PARTITION BY RANGE (order_date) with monthly
-- partitions, since fact_orders is by far the highest-volume, highest-churn
-- table and most analytical queries filter on a date range.
CREATE TABLE fact_orders (
    order_id                BIGINT,
    order_date              DATE NOT NULL,
    product_id              INTEGER NOT NULL REFERENCES dim_product(product_id),
    warehouse_id            INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    region_id               INTEGER NOT NULL REFERENCES dim_region(region_id),
    customer_segment_id     INTEGER NOT NULL REFERENCES dim_customer_segment(customer_segment_id),
    supplier_id             INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    transport_mode_id       INTEGER,
    order_qty               INTEGER NOT NULL,
    unit_price               NUMERIC(10,2),
    revenue                 NUMERIC(14,2),
    order_status             TEXT,
    promised_delivery_date  DATE,
    actual_delivery_date    DATE,
    is_late                 BOOLEAN,
    is_outlier_qty           BOOLEAN
);

CREATE TABLE fact_shipments (
    shipment_id             SERIAL PRIMARY KEY,
    warehouse_id            INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    supplier_id             INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    transport_mode_id       INTEGER NOT NULL REFERENCES dim_transport_mode(transport_mode_id),
    ship_date               DATE NOT NULL,
    promised_delivery_date  DATE NOT NULL,
    actual_delivery_date    DATE NOT NULL,
    n_orders                INTEGER NOT NULL,
    total_qty               NUMERIC(12,2) NOT NULL,
    distance_km             NUMERIC(10,2) NOT NULL,
    shipping_cost           NUMERIC(12,2) NOT NULL,
    is_otif                 BOOLEAN NOT NULL
);

CREATE TABLE fact_inventory_snapshot (
    snapshot_id         SERIAL PRIMARY KEY,
    snapshot_date       DATE NOT NULL,
    product_id          INTEGER NOT NULL REFERENCES dim_product(product_id),
    warehouse_id        INTEGER NOT NULL REFERENCES dim_warehouse(warehouse_id),
    inventory_on_hand   NUMERIC(12,2) NOT NULL,
    reorder_point       NUMERIC(12,2) NOT NULL,
    days_of_supply      NUMERIC(8,2) NOT NULL,
    week_demand         NUMERIC(12,2) NOT NULL
);

CREATE TABLE fact_supplier_performance (
    supplier_id             INTEGER NOT NULL REFERENCES dim_supplier(supplier_id),
    performance_month       DATE NOT NULL,
    order_count             INTEGER NOT NULL,
    on_time_count           INTEGER NOT NULL,
    fulfilled_count         INTEGER NOT NULL,
    avg_qty                 NUMERIC(10,2) NOT NULL,
    total_revenue           NUMERIC(14,2) NOT NULL,
    otif_rate               NUMERIC(5,4) NOT NULL,
    fill_rate               NUMERIC(5,4) NOT NULL,
    supplier_name            TEXT NOT NULL,
    avg_lead_time_days      NUMERIC(6,2) NOT NULL,
    defect_rate_observed    NUMERIC(6,4) NOT NULL,
    cost_variance_pct       NUMERIC(8,2) NOT NULL,
    PRIMARY KEY (supplier_id, performance_month)
);

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
