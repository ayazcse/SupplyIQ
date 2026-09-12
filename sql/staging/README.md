# sql/staging/

The staging table DDL (`staging_fact_orders_raw`) lives in
`database/schema/schema_staging.sql` rather than here, so that all schema
DDL (warehouse + staging) stays in one place next to the schema it's a
variant of. This directory is kept as part of the documented pipeline
structure (raw → staging → warehouse → marts) — see `docs/architecture.md`
for the full data-flow rationale — but intentionally contains no duplicate
copy of that DDL to avoid two files drifting out of sync.

If you're looking for the staging table definition: `database/schema/schema_staging.sql`.
If you're looking for how staging data is loaded: `src/ingestion/load_raw.py`.
If you're looking for how staging data is cleaned into the warehouse: `src/preprocessing/clean_orders.py`.
