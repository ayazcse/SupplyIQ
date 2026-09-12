-- =============================================================================
-- Warehouse-layer views: denormalized, analysis-ready views built directly on
-- top of the star schema. These exist so BI tools and ad-hoc analysts don't
-- need to re-write the same joins every time -- one view, reused everywhere.
-- =============================================================================

DROP VIEW IF EXISTS vw_order_enriched;
CREATE VIEW vw_order_enriched AS
SELECT
    o.order_id, o.order_date, o.order_qty, o.unit_price, o.revenue, o.order_status, o.is_late,
    p.sku, p.category, p.unit_cost,
    w.warehouse_name, r.region_name,
    s.supplier_name, s.archetype AS supplier_archetype,
    cs.segment_name AS customer_segment,
    tm.mode_name AS transport_mode
FROM fact_orders o
JOIN dim_product p ON p.product_id = o.product_id
JOIN dim_warehouse w ON w.warehouse_id = o.warehouse_id
JOIN dim_region r ON r.region_id = o.region_id
JOIN dim_supplier s ON s.supplier_id = o.supplier_id
JOIN dim_customer_segment cs ON cs.customer_segment_id = o.customer_segment_id
LEFT JOIN dim_transport_mode tm ON tm.transport_mode_id = o.transport_mode_id;


DROP VIEW IF EXISTS vw_supplier_scorecard;
CREATE VIEW vw_supplier_scorecard AS
SELECT
    s.supplier_id, s.supplier_name, s.country, s.is_single_source,
    AVG(fp.otif_rate) AS avg_otif,
    AVG(fp.avg_lead_time_days) AS avg_lead_time_days,
    AVG(fp.defect_rate_observed) AS avg_defect_rate,
    SUM(fp.total_revenue) AS total_revenue,
    COUNT(DISTINCT fp.performance_month) AS months_tracked
FROM dim_supplier s
JOIN fact_supplier_performance fp ON fp.supplier_id = s.supplier_id
GROUP BY s.supplier_id, s.supplier_name, s.country, s.is_single_source;


DROP VIEW IF EXISTS vw_inventory_health;
CREATE VIEW vw_inventory_health AS
SELECT
    p.sku, p.category, w.warehouse_name, r.region_name,
    AVG(f.inventory_on_hand) AS avg_inventory_on_hand,
    AVG(f.days_of_supply) AS avg_days_of_supply,
    AVG(f.inventory_on_hand) * p.unit_cost AS avg_inventory_value
FROM fact_inventory_snapshot f
JOIN dim_product p ON p.product_id = f.product_id
JOIN dim_warehouse w ON w.warehouse_id = f.warehouse_id
JOIN dim_region r ON r.region_id = w.region_id
GROUP BY p.product_id, w.warehouse_id;
