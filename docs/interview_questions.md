# Interview Preparation — 32 Questions & Answers

Answers are written to be understandable by a fresher but technically
credible — the goal is to sound like you actually built this, not like
you memorized a script.

## Architecture & Project Design

**1. Walk me through the architecture end to end.**
Raw synthetic data → staging (dirty data landed as-is) → a 14-rule data
quality engine that scores it → a cleaning step that dedupes/imputes/
normalizes → a SQLite star schema → SQL analytics (22 queries) and a
feature-engineering layer → four ML components (demand forecast, stockout
risk, supplier risk, anomaly detection) → a risk engine that combines them
with computed root-cause evidence → a rules-based recommendation engine and
a business-impact calculator → a grounded GenAI layer → exposed via FastAPI,
Streamlit, and Power BI.

**2. Why did you choose SQLite instead of Postgres?**
Zero setup friction for a portfolio project someone else needs to run in
minutes. The SQL dialect is ~95% identical, and I documented a Postgres
schema and the exact 1-line change (SQLAlchemy engine swap) needed to move
to it — I made a deliberate scope tradeoff and can explain it, rather than
it being an oversight.

**3. What would you change if this were a real production system?**
Scheduled retraining (Airflow/Prefect) instead of on-demand runs, Postgres
or a cloud warehouse instead of SQLite, a feature store instead of
recomputing the panel each run, model monitoring for drift, and a human
feedback loop on whether recommended actions were actually taken and what
happened after.

**4. What's the hardest technical problem you solved in this project?**
Getting the synthetic data to be internally coherent instead of independent
random noise per column — e.g., making stockouts happen *because* simulated
inventory ran out (a real causal chain via a vectorized weekly
demand/inventory/replenishment simulation), not because I sampled a
"stockout" flag directly. This mattered because otherwise every downstream
model would be learning from a fake signal that doesn't resemble a real
supply chain.

## SQL

**5. Why use window functions instead of subqueries or self-joins?**
They're computed in a single pass without re-scanning the table, and they
keep row-level detail alongside the aggregate (e.g., `AVG() OVER` lets you
see both the raw value and the rolling average in the same row) — a
GROUP BY would collapse that.

**6. Explain your rolling-30-day demand query.**
It uses `SUM(...) OVER (ORDER BY order_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)`
— a frame-based window that recomputes the trailing sum for every row as
the window slides forward one day at a time.

**7. How did you compute standard deviation in SQLite, which has no STDDEV()?**
`SQRT(AVG(x*x) - AVG(x)*AVG(x))` — the computational formula for population
variance, decomposed into functions SQLite does support.

**8. How would you find the median in SQL without PERCENTILE_CONT?**
I used `NTILE(4)` for quartiles in the lead-time analysis query, which
SQLite does support as a window function. For an exact median without
NTILE, you'd order the rows, count them, and pick the middle one(s) via
`ROW_NUMBER()` and a self-join or CTE.

**9. What's a CTE and why use one over a subquery?**
A named, readable temporary result set defined with `WITH`. Functionally
similar to a subquery, but readable top-to-bottom and reusable multiple
times in the same query without repeating the logic.

**10. How did you validate all 22 queries actually work?**
`scripts/run_sql_queries.py` parses the SQL file, executes every labeled
query against the live database, and fails loudly if any errors or returns
zero unexpected rows — it's part of the automated pipeline, not something I
eyeballed once.

## Python / Data Engineering

**11. Why pandas `groupby().transform()` instead of `.apply()` for rolling features?**
`transform()` returns a same-length Series aligned to the original index,
which is what you need to assign a new column back onto the DataFrame
directly. `.apply()` with certain rolling patterns can silently misalign
indices across groups — I actually hit exactly this bug during development
(a MultiIndex mismatch from `.rolling()` after `.shift()` inside a groupby)
and fixed it by switching to `transform(lambda s: s.shift(1).rolling(4).mean())`.

**12. How do you avoid feature leakage in a time-series ML pipeline?**
Two things: (a) every lag/rolling feature is explicitly shifted by 1+
periods before any window is computed, so "this week's feature" only ever
uses data available before this week; (b) train/test splits are always by
calendar time, never a random row shuffle.

**13. Why inject data quality issues instead of using naturally messy data?**
Because I control the ground truth — I know exactly which rows are
duplicated, null, or mis-cased, so I can verify the data-quality engine
actually catches the right rows at close to the right rate, instead of just
trusting that a report "looks reasonable."

**14. Walk me through your ETL cleaning logic for one column.**
`unit_price`: cast to numeric (coercing bad strings to NaN), take absolute
value to fix sign-error negatives, then impute any remaining nulls from
that product's catalog price in `dim_product` — never a global mean, which
would ignore the product's actual price point.

## Data Modeling

**15. Why a star schema instead of a normalized (3NF) schema?**
Analytical queries join a small number of large fact tables to several
small dimension tables — a star schema minimizes joins and keeps query
plans simple and fast for exactly that access pattern, at the cost of some
denormalization (acceptable since dimensions here are slowly changing).

**16. Why is there a bridge table between supplier, product, and warehouse?**
Because that relationship is many-to-many-to-many in reality — a supplier
can supply multiple products into multiple warehouses, and a product can
have multiple approved suppliers. A bridge table is the standard way to
model that without forcing an artificial one-to-many assumption.

**17. Why exclude `archetype` from your ML features?**
It's the label I used to *generate* supplier reliability, so including it
would let every model just look up the answer instead of learning from
the actual behavioral signals (OTIF, lead time, defects) a real model would
have to rely on. This is a data-leakage discipline point, not a modeling
detail.

## Power BI / DAX

**18. Why is your supplier risk score computed in Python, not DAX?**
Because it blends multiple weighted business rules with conditional logic
that's easiest to keep in one auditable, testable place — duplicating that
formula in DAX would create two sources of truth for the same number that
could silently drift apart.

**19. What's the difference between a calculated column and a measure in DAX?**
A calculated column is computed row-by-row at data-refresh time and stored
in the model (uses more memory, but works in a row context like a slicer);
a measure is computed on the fly at query time using the current filter
context and is the right choice for aggregations like `[Total Revenue]`.

**20. Explain your Revenue YoY % measure.**
It uses `SAMEPERIODLASTYEAR(dim_date[date])` inside a `CALCULATE()` to
recompute `[Total Revenue]` as if the filter context were shifted back one
year, then compares that to the current-context revenue — this only works
correctly because `dim_date` is marked as an official Date Table.

## Forecasting & ML

**21. Why compare against a baseline instead of just reporting the LightGBM metrics?**
A model's absolute error means nothing without a reference point — WAPE of
56% sounds bad in isolation, but next to a 61% baseline it's clearly an
improvement, and that comparison is what actually demonstrates the model
adds value.

**22. Why WAPE over MAPE as your primary forecasting metric?**
MAPE's denominator is the actual value, so it blows up (or is undefined)
for near-zero-demand weeks, which are common at SKU level. WAPE sums
absolute errors and absolute actuals separately before dividing, so it's
far more stable when many observations are small.

**23. Your stockout model's ROC-AUC is only 0.67 — is that a good model?**
It's an honest one. It's well above the 0.5 random baseline, meaning the
features genuinely carry signal, but a meaningful share of the target is
driven by a stochastic weekly demand spike that by design has no leading
indicator in the prior week — so a much higher AUC would actually be a red
flag for leakage, not a better model.

**24. Why LightGBM over a deep learning approach here?**
Tabular data with a moderate number of engineered features and no
sequential/text/image structure — gradient boosting typically matches or
beats deep learning on this kind of data, trains in seconds instead of
requiring a GPU, and is far more interpretable via feature importances.

## Anomaly Detection & Explainability

**25. Why two anomaly detection methods instead of one?**
They catch different failure modes: Isolation Forest finds unusual
*combinations* across several features at once; a rolling z-score finds a
single metric deviating sharply from its own history and works even when
there's too little data for the multivariate model to trust.

**26. How do you explain a supplier's risk score to a non-technical manager?**
I break the rule-based formula into its weighted components (OTIF gap,
defect rate, lead-time level, lead-time trend, single-source flag, cost
variance) and show which ones contributed the most points — that's more
useful to an ops manager than a single opaque "84/100."

## GenAI

**27. How do you stop the AI Analyst from making things up?**
It's retrieve-then-generate: I compute the actual supplier/SKU/risk/impact
data first, and the LLM (or the local template, if no API key is
configured) is only allowed to explain that pre-computed context — the
system prompt explicitly instructs it to say "insufficient evidence" rather
than guess, and the local fallback mode enforces that mechanically since
every number in its templates is pulled directly from the retrieved data.

**28. What happens if someone asks a question with no matching data?**
Both the LLM and local-fallback paths return a structured "insufficient
evidence" response rather than inventing an answer — I tested this
directly by simulating an empty context.

**29. Why build a local fallback mode at all instead of requiring an API key?**
So the project is fully demonstrable — clone it, run the pipeline, and the
AI Analyst just works — without anyone needing to pay for or configure an
LLM API key to see the grounded-retrieval design in action.

## Business Impact & Limitations

**30. How did you calculate the ₹238M annual risk exposure figure?**
Three components, each from a documented formula: lost margin on
stockout/partial units (using an assumed 35% margin rate), holding cost on
inventory carrying more than 2x the network's own median days-of-supply
(using an assumed 22% annual holding cost rate), and the cost premium of
Air freight vs. Road freight on the same distance, annualized from 3 years
of simulated shipments.

**31. Is that number real?**
No — it's clearly labeled "estimated/simulated" everywhere it appears. It's
built on synthetic data using documented, stated assumptions specifically
to demonstrate the *method* a real analyst would use on real company data,
not to claim an actual financial result.

**32. What's the biggest limitation of this project, honestly?**
The data is synthetic, so however coherent the simulation is, it can't
capture the messiness and edge cases of a real company's actual ERP/WMS
data. I'd want to pressure-test every model and rule against real data
before trusting any of these numbers in an actual business decision — this
project demonstrates the pipeline and methodology, not a validated real-
world result.
