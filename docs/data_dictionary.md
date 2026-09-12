# Data Dictionary

## Scale rationale

The original project brief suggested round-number targets (100,000+ orders,
5,000+ supplier relationships, etc.). Rather than force arbitrary numbers,
each entity count was chosen to be internally consistent for a **mid-size
distribution company** and then the simulation was allowed to produce
whatever transaction volume that implies:

| Entity | Count | Rationale |
|---|---|---|
| Regions | 10 | Enough for meaningful regional comparison without diluting per-region volume. |
| Warehouses | 22 | ~2 per region, some regions get more (larger markets). |
| Products (SKUs) | 120 | Realistic catalog size for a focused mid-size distributor, across 8 categories. |
| Suppliers | 60 | ~2 suppliers per product on average (see bridge table below), a realistic multi-sourcing ratio. |
| Supplier-product-warehouse links | ~1,500-1,700 (varies by seed) | NOT forced to 5,000 -- with 120 products x 1-3 suppliers x 3-11 warehouses each, ~1,600 is the number that actually reflects a coherent business, not an arbitrary target. Forcing 5,000 would have meant duplicating relationships or inventing products/suppliers that don't otherwise exist in the simulation. |
| Orders | 170,000+ | Emerges from the weekly demand simulation (see below), not set directly -- exceeds the "100,000+" target. |
| Shipments | 24,000 | Orders consolidated into shipments (~7 orders/shipment on average), sampled to a round target. |
| Inventory snapshots | 12,000 | Monthly-cadence samples across all product-warehouse pairs over 3 years. |

## How the data was generated (methodology)

1. **Dimensions first** (`src/data_generation/generate_dimensions.py`):
   regions, warehouses, products, suppliers. Suppliers are NOT independently
   randomized per column -- each is drawn from one of four *archetypes*
   (excellent/reliable/average/risky, weighted 15/40/30/15%) so that a bad
   supplier is consistently bad across OTIF, lead time, defects, AND cost,
   mirroring how real supplier risk clusters rather than behaving as
   independent noise.
2. **Weekly demand/inventory simulation** (`src/data_generation/generate_facts.py`):
   for every valid (product, warehouse) pair, 158 weeks of demand,
   inventory, and replenishment are simulated with numpy, vectorized across
   all pairs simultaneously. Reorder points and quantities are inventory-
   policy formulas (not random), so stockouts happen *because* demand
   exceeded available stock plus incoming pipeline -- a causal chain, not a
   coin flip.
3. **Two deliberate shock events** are injected into the simulation (not
   into the output afterward): a supplier lead-time/OTIF collapse for two
   "reliable" suppliers (Jul-Sep 2024) and a demand surge for Electronics in
   two regions (Q4 2024). These exist so the downstream root-cause and risk
   models have a genuine, known-answer signal to detect -- and the pipeline
   verifiably does detect them (see `docs/ml_methodology.md`).
4. **Order-line explosion**: weekly aggregate demand/unmet-demand per pair
   is exploded into individual order transactions with randomized order
   sizes (Dirichlet split), dates within the week, customer segments,
   transport modes, and promised/actual delivery dates derived from the
   *same* simulated lead times and OTIF probabilities used for inventory.
5. **Data-quality issues injected last, deliberately** (`inject_data_quality_issues`):
   nulls (~0.4-0.7%), duplicate order IDs (~0.4%), extreme quantity outliers
   (~0.2%), sign-error negative prices (~0.05%), and inconsistent status
   casing (~0.3%) -- see the "Known Injected Issues" table below.

## Known Injected Issues (ground truth for the data-quality engine)

| Issue | Rate (approx.) | Where |
|---|---|---|
| Null `unit_price` | 0.4% | fact_orders |
| Null `transport_mode_id` | 0.3% | fact_orders |
| Duplicate `order_id` | 0.4% | fact_orders |
| Extreme quantity outlier (fat-finger) | 0.2% | fact_orders |
| Negative `unit_price` (sign error) | 0.05% | fact_orders |
| Inconsistent status casing (`fulfilled`, `STOCKOUT`, `partial `) | 0.3% | fact_orders |

The data-quality engine (`src/validation/data_quality.py`) scored **99.9%**
against these on the reference run -- verify the score matches roughly this
range after any regeneration; a big deviation would indicate a bug in
either the injection or detection logic.

## Column reference (key tables)

### dim_product
| Column | Type | Description | Example |
|---|---|---|---|
| product_id | int | Surrogate key | 1 |
| sku | text | Business key | SKU-00001 |
| category | text | One of 8 categories | Electronics |
| unit_cost / unit_price | float | Cost basis / list price | 45.20 / 78.50 |
| base_daily_demand | float | Gamma-distributed baseline demand rate used to seed the simulation | 32.4 |
| is_seasonal | bool | Apparel/Packaged Foods/Personal Care = True | True |
| shelf_life_days | int | Used narratively; not currently consumed by any model | 180 |

### dim_supplier
| Column | Type | Description |
|---|---|---|
| archetype | text | Generation-time label (excellent/reliable/average/risky) -- **excluded from all ML model features** to avoid leaking the synthetic ground truth into the model it's meant to validate. |
| base_otif_rate, base_lead_time_days, lead_time_volatility, defect_rate, cost_volatility | float | Archetype-driven baseline parameters that seed the weekly simulation. |
| is_single_source | bool | 12% of suppliers -- used for concentration-risk scoring. |

### fact_orders
| Column | Type | Description |
|---|---|---|
| order_status | text | Fulfilled / Stockout / Partial (canonical) -- inconsistently cased in ~0.3% of raw rows by design. |
| is_late | bool | Actual delivery date later than promised. |
| is_outlier_qty | bool | Added during preprocessing; flags (does not drop) extreme quantities via IQR. |

### fact_inventory_snapshot
| Column | Type | Description |
|---|---|---|
| days_of_supply | float | inventory_on_hand / (weekly demand / 7); the core inventory-health metric used throughout the risk engine. |

Full column-by-column listings for every table are in the CSV headers
themselves (`data/synthetic/*.csv`) combined with the schema DDL in
`database/schema/schema_sqlite.sql`, which documents type and nullability
for every field.
