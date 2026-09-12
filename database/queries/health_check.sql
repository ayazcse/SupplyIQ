-- Quick operational health check for the SupplyIQ database.
-- Run with: sqlite3 database/supplyiq.db < database/queries/health_check.sql

SELECT 'dim_product' AS table_name, COUNT(*) AS row_count FROM dim_product
UNION ALL SELECT 'dim_supplier', COUNT(*) FROM dim_supplier
UNION ALL SELECT 'dim_warehouse', COUNT(*) FROM dim_warehouse
UNION ALL SELECT 'dim_region', COUNT(*) FROM dim_region
UNION ALL SELECT 'fact_orders', COUNT(*) FROM fact_orders
UNION ALL SELECT 'fact_shipments', COUNT(*) FROM fact_shipments
UNION ALL SELECT 'fact_inventory_snapshot', COUNT(*) FROM fact_inventory_snapshot
UNION ALL SELECT 'fact_supplier_performance', COUNT(*) FROM fact_supplier_performance
UNION ALL SELECT 'staging_fact_orders_raw', COUNT(*) FROM staging_fact_orders_raw;

-- Referential integrity spot-check: any fact_orders rows pointing at a
-- product_id that doesn't exist in dim_product? (Should always be 0 --
-- if not, the preprocessing step has a bug.)
SELECT COUNT(*) AS orphan_product_rows
FROM fact_orders o
LEFT JOIN dim_product p ON p.product_id = o.product_id
WHERE p.product_id IS NULL;
