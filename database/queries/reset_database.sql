-- Drops all SupplyIQ tables and views, for a clean re-run of the schema +
-- ingestion steps without deleting the .db file itself.
-- Run with: sqlite3 database/supplyiq.db < database/queries/reset_database.sql
-- (Equivalent to `rm database/supplyiq.db` before re-running the pipeline,
-- which is what scripts/run_pipeline.py does implicitly by recreating all
-- tables with DROP TABLE IF EXISTS in the schema files -- this script is
-- provided for when you want to reset without touching the file itself,
-- e.g. if another process has the .db file open.)

DROP VIEW IF EXISTS vw_order_enriched;
DROP VIEW IF EXISTS vw_supplier_scorecard;
DROP VIEW IF EXISTS vw_inventory_health;
DROP VIEW IF EXISTS mart_monthly_executive_summary;

DROP TABLE IF EXISTS fact_orders;
DROP TABLE IF EXISTS fact_shipments;
DROP TABLE IF EXISTS fact_inventory_snapshot;
DROP TABLE IF EXISTS fact_supplier_performance;
DROP TABLE IF EXISTS staging_fact_orders_raw;
DROP TABLE IF EXISTS bridge_supplier_product;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_region;
DROP TABLE IF EXISTS dim_warehouse;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_supplier;
DROP TABLE IF EXISTS dim_customer_segment;
DROP TABLE IF EXISTS dim_transport_mode;
