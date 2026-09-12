-- Staging schema: mirrors the RAW synthetic extract as closely as possible
-- (mostly TEXT columns) so ingestion never fails on dirty data -- nulls,
-- negative numbers, inconsistent casing, and duplicate keys are all accepted
-- here and only resolved during the validation + preprocessing stages.
DROP TABLE IF EXISTS staging_fact_orders_raw;
CREATE TABLE staging_fact_orders_raw (
    order_id                TEXT,
    order_date              TEXT,
    product_id              TEXT,
    warehouse_id            TEXT,
    region_id               TEXT,
    customer_segment_id     TEXT,
    supplier_id             TEXT,
    transport_mode_id       TEXT,
    order_qty               TEXT,
    unit_price              TEXT,
    revenue                 TEXT,
    order_status            TEXT,
    promised_delivery_date  TEXT,
    actual_delivery_date    TEXT,
    is_late                 TEXT
);
