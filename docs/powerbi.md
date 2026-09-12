# SupplyIQ — Power BI Dashboard Guide

Power BI Desktop only runs on Windows, and `.pbix` files are a binary format
that can't be authored by a script. This guide gets you from the exported
CSVs to a working executive dashboard in ~20-30 minutes of manual steps —
everything else (the data, the relationships, the DAX) is fully specified
below so there's no guesswork.

## 1. Data source

All star-schema tables are pre-exported to `dashboard/powerbi_exports/*.csv`
(generated directly from the SQLite warehouse, so they match the SQL layer
exactly). You can also connect Power BI directly to `database/supplyiq.db`
via the "SQLite ODBC Driver" if you prefer a live connection over static
CSVs — install the driver from http://www.ch-werner.de/sqliteodbc/ first.

**Simplest path (recommended): Import the CSVs.**

1. Open Power BI Desktop → **Get Data → Text/CSV**.
2. Import all 11 files from `dashboard/powerbi_exports/`:
   `dim_date, dim_region, dim_warehouse, dim_product, dim_supplier,
   dim_customer_segment, dim_transport_mode, fact_orders, fact_shipments,
   fact_inventory_snapshot, fact_supplier_performance`.
3. In **Power Query Editor**, set data types explicitly (Power BI sometimes
   mis-infers): `order_date`, `promised_delivery_date`, `actual_delivery_date`,
   `ship_date`, `snapshot_date` → Date; all `*_id` columns → Whole Number;
   `is_late`, `is_otif`, `is_seasonal`, `is_single_source`, `is_outlier_qty` →
   True/False.
4. Click **Close & Apply**.

## 2. Data model (relationships)

Power BI should mostly auto-detect these via matching column names, but
verify each relationship is **one-to-many** from dimension → fact, with the
dimension on the "1" side:

| From (1 side)         | To (many side)              | Join column          |
|------------------------|------------------------------|-----------------------|
| dim_date               | fact_orders                  | date ↔ order_date     |
| dim_product             | fact_orders                  | product_id            |
| dim_warehouse           | fact_orders                  | warehouse_id          |
| dim_region              | fact_orders                  | region_id             |
| dim_customer_segment    | fact_orders                  | customer_segment_id   |
| dim_supplier            | fact_orders                  | supplier_id           |
| dim_transport_mode      | fact_orders                  | transport_mode_id     |
| dim_warehouse           | fact_shipments                | warehouse_id          |
| dim_supplier            | fact_shipments                | supplier_id           |
| dim_transport_mode      | fact_shipments                | transport_mode_id     |
| dim_product             | fact_inventory_snapshot       | product_id            |
| dim_warehouse           | fact_inventory_snapshot       | warehouse_id          |
| dim_supplier            | fact_supplier_performance      | supplier_id           |

This is a **star schema**: every fact table joins only to dimensions, never
fact-to-fact. If Power BI creates a relationship as many-to-many, fix it
manually in the Model view — it means a dimension key isn't unique (check
`dim_date.date` is deduplicated, which it is by construction).

Mark `dim_date` as a **Date Table** (Table tools → Mark as Date Table) so
time-intelligence DAX functions (SAMEPERIODLASTYEAR, DATESYTD, etc.) work.

## 3. DAX Measures

Create a new table (Modeling → New Table, name it `_Measures`, formula `=1`)
to hold all measures cleanly separate from the data tables. Add these:

```dax
Total Orders = COUNTROWS(fact_orders)

Total Revenue = SUM(fact_orders[revenue])

OTIF % =
DIVIDE(
    CALCULATE(COUNTROWS(fact_orders), fact_orders[is_late] = FALSE),
    COUNTROWS(fact_orders)
)

Fill Rate % =
DIVIDE(
    CALCULATE(COUNTROWS(fact_orders), fact_orders[order_status] = "Fulfilled"),
    COUNTROWS(fact_orders)
)

Stockout % =
DIVIDE(
    CALCULATE(COUNTROWS(fact_orders), fact_orders[order_status] = "Stockout"),
    COUNTROWS(fact_orders)
)

Avg Inventory On Hand = AVERAGE(fact_inventory_snapshot[inventory_on_hand])

Avg Days Inventory Outstanding = AVERAGE(fact_inventory_snapshot[days_of_supply])

Inventory Turnover (Annualized) =
VAR UnitsSold = SUM(fact_orders[order_qty])
VAR AvgInv = AVERAGE(fact_inventory_snapshot[inventory_on_hand])
RETURN DIVIDE(UnitsSold, AvgInv * 3)   -- dataset spans 3 years; adjust divisor if you change the horizon

Avg Supplier Lead Time = AVERAGE(fact_supplier_performance[avg_lead_time_days])

Supplier Risk Score (Avg) = AVERAGE(fact_supplier_performance[otif_rate])  -- see note below

At-Risk Revenue =
CALCULATE(
    SUM(fact_orders[revenue]),
    fact_orders[order_status] IN {"Stockout", "Partial"}
)

Revenue YoY % =
VAR CurrYear = [Total Revenue]
VAR PrevYear = CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(dim_date[date]))
RETURN DIVIDE(CurrYear - PrevYear, PrevYear)

Revenue MoM % =
VAR CurrMonth = [Total Revenue]
VAR PrevMonth = CALCULATE([Total Revenue], DATEADD(dim_date[date], -1, MONTH))
RETURN DIVIDE(CurrMonth - PrevMonth, PrevMonth)

Rolling 30D Demand =
CALCULATE(
    SUM(fact_orders[order_qty]),
    DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -30, DAY)
)

Forecast Accuracy (WAPE) = 1 - 0.5631   -- pulled from data/processed/forecast_model_comparison.csv (LightGBM WAPE); update after each retrain, or import that CSV as its own table and reference it directly

Excess Inventory Value =
SUMX(
    FILTER(fact_inventory_snapshot, fact_inventory_snapshot[days_of_supply] > 15),
    fact_inventory_snapshot[inventory_on_hand] * RELATED(dim_product[unit_cost])
)
```

> **Note on Supplier Risk Score:** the *real* supplier risk score (rule-based
> + ML) is computed in Python (`src/models/supplier_risk_model.py`) because it
> blends multiple weighted signals with documented business logic that's
> easiest to keep in one auditable place. Import
> `data/processed/supplier_risk_full_history.csv` as an additional table and
> use its `rule_based_risk_score` column directly in Power BI rather than
> re-deriving it in DAX — this avoids having two different formulas for the
> same number in two different places.

## 4. Dashboard pages

### Page 1 — Executive Command Center
KPI cards: Total Orders, OTIF %, Fill Rate %, Stockout %, At-Risk Revenue,
Avg Supplier Lead Time, Forecast Accuracy. Visuals: line chart of monthly
risk-event rate (import `data/processed/sql_query_samples/q18_risk_trend...csv`
or recreate via `Risk Trend` DAX measure over `dim_date`), a filled map of
`dim_region` colored by stockout %, a bar chart ranking suppliers by risk
score (from the imported `supplier_risk_full_history.csv`), and a table of
the top 5 items from `data/processed/recommendations.json` (flatten to CSV
first, or paste as a manual table for the demo).

### Page 2 — Demand Intelligence
Line chart: Actual vs Predicted (import `forecast_actual_vs_predicted.csv`),
demand trend by month, SKU ranking by volume, seasonality index by category
(from SQL query Q14), demand volatility (Q4) as a table.

### Page 3 — Inventory Intelligence
KPI cards: Stockout %, Inventory Turnover, Avg Days of Supply. A heatmap
matrix (product category × warehouse) colored by `days_of_supply`. Table of
high-risk SKUs from `unified_sku_risk.json` (flatten to CSV for import).

### Page 4 — Supplier Intelligence
Bar chart of supplier risk score, scatter plot of OTIF vs. lead time (risk
matrix), defect rate trend, supplier concentration (single-source revenue
share, from SQL Q21).

### Page 5 — Logistics Intelligence
Delivery performance by transport mode (Q22 lead-time quartiles), delay
rate by warehouse (Q16), shipment cost breakdown (Q12).

### Page 6 — AI Recommendations
A table visual bound to a flattened `recommendations.json` → CSV, with
columns Issue / Evidence / Recommended Action / Expected Benefit / Urgency,
conditionally formatted by urgency (red/orange/yellow).

## 5. Flattening JSON outputs for Power BI

Power BI's CSV/Text connector can't read nested JSON evidence lists well.
Run this once to produce flat, Power-BI-friendly CSVs:

```powershell
python scripts/flatten_json_for_powerbi.py
```

This writes `dashboard/powerbi_exports/recommendations_flat.csv`,
`unified_sku_risk_flat.csv`, and `unified_supplier_risk_flat.csv` (evidence
lists joined into a single semicolon-separated text column).

## 6. Refreshing the dashboard after re-running the pipeline

Re-run `python scripts/run_pipeline.py`, then in Power BI: **Home → Refresh**.
Since the CSVs are re-exported to the same file paths, Power BI will pick up
the new data without needing to reconfigure any visuals or relationships.
