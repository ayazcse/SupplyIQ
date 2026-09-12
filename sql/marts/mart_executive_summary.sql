-- =============================================================================
-- Executive summary mart: one row per month with the headline KPIs an
-- executive dashboard's top row needs. Built on top of the warehouse views
-- (sql/warehouse/create_warehouse_views.sql must be run first).
-- =============================================================================

DROP VIEW IF EXISTS mart_monthly_executive_summary;
CREATE VIEW mart_monthly_executive_summary AS
SELECT
    strftime('%Y-%m', order_date) AS month,
    COUNT(*) AS total_orders,
    SUM(revenue) AS total_revenue,
    ROUND(100.0 * SUM(CASE WHEN is_late = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS otif_pct,
    ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(order_status)) = 'fulfilled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS fill_rate_pct,
    ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(order_status)) = 'stockout' THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct
FROM fact_orders
GROUP BY month
ORDER BY month;
