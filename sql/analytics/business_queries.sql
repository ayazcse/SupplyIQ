-- =============================================================================
-- SupplyIQ — Business Analytics SQL Query Library
-- =============================================================================
-- 22 production-style analytical queries answering real supply-chain
-- questions. Each query is preceded by a comment stating the business
-- question it answers. Deliberately demonstrates: CTEs, window functions
-- (ROW_NUMBER, RANK, LAG, AVG/SUM OVER, NTILE, PERCENT_RANK), rolling
-- metrics, conditional aggregation, and date intelligence.
--
-- Run individually, or all at once via: python scripts/run_sql_queries.py
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Q1. Top suppliers by OTIF (On-Time-In-Full) rate, minimum volume threshold
-- -----------------------------------------------------------------------------
-- Business question: which suppliers should we hold up as the reliability benchmark?
SELECT
    s.supplier_name,
    s.country,
    COUNT(*) AS total_orders,
    ROUND(AVG(CASE WHEN o.is_late = 0 THEN 1.0 ELSE 0.0 END), 4) AS otif_rate,
    RANK() OVER (ORDER BY AVG(CASE WHEN o.is_late = 0 THEN 1.0 ELSE 0.0 END) DESC) AS otif_rank
FROM fact_orders o
JOIN dim_supplier s ON s.supplier_id = o.supplier_id
GROUP BY s.supplier_id, s.supplier_name, s.country
HAVING COUNT(*) >= 200
ORDER BY otif_rate DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q2. Worst suppliers by late-shipment rate (shipment-level, not order-level)
-- -----------------------------------------------------------------------------
-- Business question: which suppliers' shipments are most frequently late, and how costly are they?
SELECT
    s.supplier_name,
    COUNT(*) AS total_shipments,
    ROUND(AVG(CASE WHEN sh.is_otif = 0 THEN 1.0 ELSE 0.0 END), 4) AS late_rate,
    ROUND(AVG(sh.shipping_cost), 2) AS avg_shipping_cost,
    ROUND(SUM(sh.shipping_cost), 2) AS total_shipping_cost
FROM fact_shipments sh
JOIN dim_supplier s ON s.supplier_id = sh.supplier_id
GROUP BY s.supplier_id, s.supplier_name
HAVING COUNT(*) >= 50
ORDER BY late_rate DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q3. Rolling 30-day demand per product (window function: SUM OVER date range)
-- -----------------------------------------------------------------------------
-- Business question: what is the trailing-30-day demand trend for our top SKU?
WITH daily_demand AS (
    SELECT product_id, order_date, SUM(order_qty) AS daily_qty
    FROM fact_orders
    WHERE product_id = (SELECT product_id FROM fact_orders GROUP BY product_id ORDER BY SUM(order_qty) DESC LIMIT 1)
    GROUP BY product_id, order_date
)
SELECT
    order_date,
    daily_qty,
    ROUND(AVG(daily_qty) OVER (ORDER BY order_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 1) AS rolling_30d_avg_demand,
    SUM(daily_qty) OVER (ORDER BY order_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW) AS rolling_30d_total_demand
FROM daily_demand
ORDER BY order_date;


-- -----------------------------------------------------------------------------
-- Q4. SKU demand volatility (coefficient of variation) -- identifies erratic-demand products
-- -----------------------------------------------------------------------------
-- Business question: which SKUs have the least predictable demand (hardest to forecast/stock)?
WITH monthly AS (
    SELECT product_id, strftime('%Y-%m', order_date) AS ym, SUM(order_qty) AS qty
    FROM fact_orders
    GROUP BY product_id, ym
),
stats AS (
    SELECT product_id, AVG(qty) AS mean_qty,
           -- population stddev via sqrt(E[x^2]-E[x]^2), since SQLite has no STDDEV()
           SQRT(AVG(qty*qty) - AVG(qty)*AVG(qty)) AS stddev_qty
    FROM monthly
    GROUP BY product_id
)
SELECT p.sku, p.category, s.mean_qty, s.stddev_qty,
       ROUND(s.stddev_qty / NULLIF(s.mean_qty, 0), 3) AS coefficient_of_variation
FROM stats s
JOIN dim_product p ON p.product_id = s.product_id
ORDER BY coefficient_of_variation DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q5. Regional stockout rate
-- -----------------------------------------------------------------------------
-- Business question: which regions suffer the most stockouts, proportionally?
SELECT
    r.region_name,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN LOWER(TRIM(o.order_status)) = 'stockout' THEN 1 ELSE 0 END) AS stockout_orders,
    ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(o.order_status)) = 'stockout' THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct
FROM fact_orders o
JOIN dim_region r ON r.region_id = o.region_id
GROUP BY r.region_id, r.region_name
ORDER BY stockout_rate_pct DESC;


-- -----------------------------------------------------------------------------
-- Q6. Supplier lead-time instability (month-over-month volatility)
-- -----------------------------------------------------------------------------
-- Business question: whose lead times swing the most month to month (unpredictability, not just slowness)?
WITH lead_by_month AS (
    SELECT supplier_id, supplier_name, performance_month, avg_lead_time_days
    FROM fact_supplier_performance
)
SELECT
    supplier_name,
    ROUND(AVG(avg_lead_time_days), 2) AS avg_lead_time,
    ROUND(SQRT(AVG(avg_lead_time_days*avg_lead_time_days) - AVG(avg_lead_time_days)*AVG(avg_lead_time_days)), 2) AS lead_time_stddev
FROM lead_by_month
GROUP BY supplier_id, supplier_name
HAVING COUNT(*) >= 12
ORDER BY lead_time_stddev DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q7. Inventory turnover (annualized) per product
-- -----------------------------------------------------------------------------
-- Business question: how efficiently is capital cycling through inventory for each product?
WITH annual_demand AS (
    SELECT product_id, SUM(order_qty) AS total_units_sold
    FROM fact_orders
    GROUP BY product_id
),
avg_inv AS (
    SELECT product_id, AVG(inventory_on_hand) AS avg_inventory
    FROM fact_inventory_snapshot
    GROUP BY product_id
)
SELECT p.sku, p.category,
       ad.total_units_sold,
       ROUND(ai.avg_inventory, 1) AS avg_inventory_on_hand,
       ROUND(ad.total_units_sold / (ai.avg_inventory * 3.0), 2) AS annualized_inventory_turnover  -- /3 because 3 yrs of data
FROM annual_demand ad
JOIN avg_inv ai ON ai.product_id = ad.product_id
JOIN dim_product p ON p.product_id = ad.product_id
ORDER BY annualized_inventory_turnover ASC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q8. Excess inventory (days-of-supply well beyond what's needed)
-- -----------------------------------------------------------------------------
-- Business question: where is working capital being tied up unnecessarily?
SELECT
    p.sku, w.warehouse_name,
    ROUND(AVG(f.days_of_supply), 1) AS avg_days_of_supply,
    ROUND(AVG(f.inventory_on_hand) * p.unit_cost, 2) AS avg_inventory_value
FROM fact_inventory_snapshot f
JOIN dim_product p ON p.product_id = f.product_id
JOIN dim_warehouse w ON w.warehouse_id = f.warehouse_id
GROUP BY p.product_id, w.warehouse_id
HAVING AVG(f.days_of_supply) > 18
ORDER BY avg_inventory_value DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q9. Slow-moving inventory (low turnover AND high days of supply)
-- -----------------------------------------------------------------------------
-- Business question: which SKU-warehouse combos are candidates for markdown / reallocation?
WITH inv AS (
    SELECT product_id, warehouse_id, AVG(days_of_supply) AS avg_dos, AVG(inventory_on_hand) AS avg_inv
    FROM fact_inventory_snapshot GROUP BY product_id, warehouse_id
),
demand AS (
    SELECT product_id, warehouse_id, SUM(order_qty) AS units_sold
    FROM fact_orders GROUP BY product_id, warehouse_id
)
SELECT p.sku, wh.warehouse_name, i.avg_dos, COALESCE(d.units_sold, 0) AS units_sold_3yr
FROM inv i
JOIN dim_product p ON p.product_id = i.product_id
JOIN dim_warehouse wh ON wh.warehouse_id = i.warehouse_id
LEFT JOIN demand d ON d.product_id = i.product_id AND d.warehouse_id = i.warehouse_id
WHERE i.avg_dos > 10 AND COALESCE(d.units_sold, 0) < (SELECT AVG(units_sold) * 0.6 FROM demand)
ORDER BY i.avg_dos DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q10. High-risk SKU identification (composite: stockout rate + demand volatility)
-- -----------------------------------------------------------------------------
-- Business question: which SKUs combine unpredictable demand with frequent stockouts?
WITH sku_stockout AS (
    SELECT product_id,
           ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(order_status)) IN ('stockout','partial') THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct,
           COUNT(*) AS n_orders
    FROM fact_orders GROUP BY product_id
),
sku_volatility AS (
    SELECT product_id, AVG(qty) AS mean_qty, SQRT(AVG(qty*qty)-AVG(qty)*AVG(qty)) AS sd_qty
    FROM (SELECT product_id, strftime('%Y-%m', order_date) ym, SUM(order_qty) qty FROM fact_orders GROUP BY product_id, ym)
    GROUP BY product_id
)
SELECT p.sku, p.category, so.stockout_rate_pct, so.n_orders,
       ROUND(sv.sd_qty / NULLIF(sv.mean_qty,0), 2) AS demand_cv,
       ROUND(so.stockout_rate_pct * (1 + sv.sd_qty / NULLIF(sv.mean_qty,0)), 2) AS composite_risk_score
FROM sku_stockout so
JOIN sku_volatility sv ON sv.product_id = so.product_id
JOIN dim_product p ON p.product_id = so.product_id
WHERE so.n_orders >= 100
ORDER BY composite_risk_score DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q11. High-risk supplier identification (composite rule-based score)
-- -----------------------------------------------------------------------------
-- Business question: which suppliers most need a business review this quarter?
SELECT
    s.supplier_name, s.country, s.is_single_source,
    ROUND(AVG(fp.otif_rate), 3) AS avg_otif,
    ROUND(AVG(fp.avg_lead_time_days), 1) AS avg_lead_time,
    ROUND(AVG(fp.defect_rate_observed), 4) AS avg_defect_rate,
    ROUND(
        (1 - AVG(fp.otif_rate)) * 40 +
        (AVG(fp.defect_rate_observed) * 100) * 3 +
        (AVG(fp.avg_lead_time_days) / 20.0) * 15 +
        (CASE WHEN s.is_single_source THEN 10 ELSE 0 END)
    , 1) AS supplier_risk_score_sql_approx
FROM fact_supplier_performance fp
JOIN dim_supplier s ON s.supplier_id = fp.supplier_id
GROUP BY s.supplier_id, s.supplier_name, s.country, s.is_single_source
ORDER BY supplier_risk_score_sql_approx DESC
LIMIT 10;


-- -----------------------------------------------------------------------------
-- Q12. Cost leakage: expedited (Air) shipping cost as a share of total logistics spend
-- -----------------------------------------------------------------------------
-- Business question: how much are we overspending on emergency/expedited freight?
SELECT
    tm.mode_name,
    COUNT(*) AS shipment_count,
    ROUND(SUM(sh.shipping_cost), 2) AS total_cost,
    ROUND(100.0 * SUM(sh.shipping_cost) / SUM(SUM(sh.shipping_cost)) OVER (), 2) AS pct_of_total_logistics_cost
FROM fact_shipments sh
JOIN dim_transport_mode tm ON tm.transport_mode_id = sh.transport_mode_id
GROUP BY tm.mode_name
ORDER BY total_cost DESC;


-- -----------------------------------------------------------------------------
-- Q13. Order delay root causes: late orders broken down by supplier archetype & season
-- -----------------------------------------------------------------------------
-- Business question: are delays concentrated in specific supplier tiers or seasons?
SELECT
    s.archetype,
    d.month_name,
    COUNT(*) AS total_orders,
    ROUND(100.0 * SUM(o.is_late) / COUNT(*), 2) AS late_rate_pct
FROM fact_orders o
JOIN dim_supplier s ON s.supplier_id = o.supplier_id
JOIN dim_date d ON d.date = o.order_date
GROUP BY s.archetype, d.month, d.month_name
ORDER BY s.archetype, d.month;


-- -----------------------------------------------------------------------------
-- Q14. Seasonality: monthly demand index relative to yearly average, by category
-- -----------------------------------------------------------------------------
-- Business question: which categories are genuinely seasonal vs. flat year-round?
WITH monthly_cat AS (
    SELECT p.category, strftime('%m', o.order_date) AS month, SUM(o.order_qty) AS qty
    FROM fact_orders o JOIN dim_product p ON p.product_id = o.product_id
    GROUP BY p.category, month
),
cat_avg AS (
    SELECT category, AVG(qty) AS avg_monthly_qty FROM monthly_cat GROUP BY category
)
SELECT mc.category, mc.month, mc.qty,
       ROUND(mc.qty / ca.avg_monthly_qty, 2) AS seasonality_index
FROM monthly_cat mc JOIN cat_avg ca ON ca.category = mc.category
ORDER BY mc.category, mc.month;


-- -----------------------------------------------------------------------------
-- Q15. Demand spikes: weeks where demand exceeded the trailing 8-week average by 50%+
-- -----------------------------------------------------------------------------
-- Business question: when and where did unplanned demand spikes actually occur?
WITH weekly AS (
    SELECT product_id, strftime('%Y-%W', order_date) AS yw, MIN(order_date) AS week_start, SUM(order_qty) AS qty
    FROM fact_orders GROUP BY product_id, yw
),
with_trailing AS (
    SELECT *, AVG(qty) OVER (PARTITION BY product_id ORDER BY week_start ROWS BETWEEN 8 PRECEDING AND 1 PRECEDING) AS trailing_avg
    FROM weekly
)
SELECT p.sku, w.week_start, w.qty, ROUND(w.trailing_avg, 1) AS trailing_8wk_avg,
       ROUND(100.0 * (w.qty - w.trailing_avg) / NULLIF(w.trailing_avg, 0), 1) AS pct_above_trailing_avg
FROM with_trailing w
JOIN dim_product p ON p.product_id = w.product_id
WHERE w.trailing_avg IS NOT NULL AND w.qty > 1.5 * w.trailing_avg
ORDER BY pct_above_trailing_avg DESC
LIMIT 20;


-- -----------------------------------------------------------------------------
-- Q16. Warehouse performance scorecard
-- -----------------------------------------------------------------------------
-- Business question: which warehouses are operational bottlenecks?
SELECT
    wh.warehouse_name, r.region_name,
    COUNT(*) AS total_orders,
    ROUND(100.0 * SUM(CASE WHEN o.is_late = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS otif_pct,
    ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(o.order_status)) = 'stockout' THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_pct,
    ROUND(SUM(o.revenue), 0) AS total_revenue
FROM fact_orders o
JOIN dim_warehouse wh ON wh.warehouse_id = o.warehouse_id
JOIN dim_region r ON r.region_id = wh.region_id
GROUP BY wh.warehouse_id, wh.warehouse_name, r.region_name
ORDER BY otif_pct ASC;


-- -----------------------------------------------------------------------------
-- Q17. Service-level (fill rate) trend over time -- month over month change
-- -----------------------------------------------------------------------------
-- Business question: is our overall service level improving or deteriorating?
WITH monthly_fill AS (
    SELECT strftime('%Y-%m', order_date) AS ym,
           ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(order_status)) = 'fulfilled' THEN 1 ELSE 0 END) / COUNT(*), 2) AS fill_rate_pct
    FROM fact_orders GROUP BY ym
)
SELECT ym, fill_rate_pct,
       LAG(fill_rate_pct) OVER (ORDER BY ym) AS prev_month_fill_rate,
       ROUND(fill_rate_pct - LAG(fill_rate_pct) OVER (ORDER BY ym), 2) AS mom_change
FROM monthly_fill
ORDER BY ym;


-- -----------------------------------------------------------------------------
-- Q18. Risk trend: monthly count of high-severity events (stockouts + late deliveries)
-- -----------------------------------------------------------------------------
-- Business question: is overall operational risk trending up or down?
SELECT
    strftime('%Y-%m', order_date) AS ym,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN LOWER(TRIM(order_status)) = 'stockout' OR is_late = 1 THEN 1 ELSE 0 END) AS risk_events,
    ROUND(100.0 * SUM(CASE WHEN LOWER(TRIM(order_status)) = 'stockout' OR is_late = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS risk_event_rate_pct
FROM fact_orders
GROUP BY ym
ORDER BY ym;


-- -----------------------------------------------------------------------------
-- Q19. Working-capital exposure: total inventory value tied up, by category
-- -----------------------------------------------------------------------------
-- Business question: where is the largest share of working capital locked up in stock?
SELECT
    p.category,
    ROUND(SUM(f.inventory_on_hand * p.unit_cost), 0) AS inventory_value,
    ROUND(100.0 * SUM(f.inventory_on_hand * p.unit_cost) / SUM(SUM(f.inventory_on_hand * p.unit_cost)) OVER (), 2) AS pct_of_total
FROM fact_inventory_snapshot f
JOIN dim_product p ON p.product_id = f.product_id
GROUP BY p.category
ORDER BY inventory_value DESC;


-- -----------------------------------------------------------------------------
-- Q20. Business impact ranking: estimated revenue at risk per product (stockout orders x avg revenue)
-- -----------------------------------------------------------------------------
-- Business question: which products carry the largest simulated revenue-at-risk from stockouts?
SELECT
    p.sku, p.category,
    COUNT(*) AS stockout_orders,
    ROUND(AVG(o.unit_price), 2) AS avg_unit_price,
    ROUND(AVG(o.order_qty), 1) AS avg_order_qty,
    ROUND(COUNT(*) * AVG(o.unit_price) * AVG(o.order_qty), 0) AS estimated_revenue_at_risk
FROM fact_orders o
JOIN dim_product p ON p.product_id = o.product_id
WHERE LOWER(TRIM(o.order_status)) = 'stockout'
GROUP BY p.product_id, p.sku, p.category
ORDER BY estimated_revenue_at_risk DESC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- Q21. Supplier concentration risk: revenue share held by single-source suppliers
-- -----------------------------------------------------------------------------
-- Business question: how exposed are we if a single-source supplier fails?
SELECT
    s.is_single_source,
    COUNT(DISTINCT s.supplier_id) AS n_suppliers,
    ROUND(SUM(o.revenue), 0) AS total_revenue,
    ROUND(100.0 * SUM(o.revenue) / SUM(SUM(o.revenue)) OVER (), 2) AS pct_of_total_revenue
FROM fact_orders o
JOIN dim_supplier s ON s.supplier_id = o.supplier_id
GROUP BY s.is_single_source;


-- -----------------------------------------------------------------------------
-- Q22. Lead-time percentile analysis by transport mode (NTILE-based quartiles)
-- -----------------------------------------------------------------------------
-- Business question: what does the full distribution (not just the average) of delivery lead time look like per mode?
WITH lead_times AS (
    SELECT tm.mode_name,
           CAST(JULIANDAY(sh.actual_delivery_date) - JULIANDAY(sh.ship_date) AS INTEGER) AS lead_days
    FROM fact_shipments sh
    JOIN dim_transport_mode tm ON tm.transport_mode_id = sh.transport_mode_id
),
quartiled AS (
    SELECT mode_name, lead_days, NTILE(4) OVER (PARTITION BY mode_name ORDER BY lead_days) AS quartile
    FROM lead_times
)
SELECT mode_name, quartile, COUNT(*) AS n, ROUND(AVG(lead_days), 1) AS avg_lead_days,
       MIN(lead_days) AS min_lead_days, MAX(lead_days) AS max_lead_days
FROM quartiled
GROUP BY mode_name, quartile
ORDER BY mode_name, quartile;
