# Business Logic

This document is the audit trail for every formula and threshold used
outside the ML models — the rules an ops manager could check by hand.

## Data quality score

`score = 100 - weighted_average_failure_rate`, where each of the 14 rules'
failure percentage is weighted by severity (CRITICAL=3, HIGH=2, MEDIUM=1,
LOW=0.5) before averaging. This means a small failure rate on a CRITICAL
rule (e.g., orphaned foreign keys) drags the score down much more than the
same failure rate on a MEDIUM rule (e.g., inconsistent status casing).
Implementation: `src/validation/data_quality.py::score_from_results`.

## Preprocessing / cleaning rules

| Rule | Action | Why |
|---|---|---|
| Duplicate `order_id` | Keep first occurrence, drop rest | Simplest deterministic policy; a real pipeline would also alert the source system. |
| Negative `unit_price` | Take absolute value | Documented assumption: sign-entry error, not a real credit. Flagged as an assumption, not asserted as fact. |
| Missing `unit_price` | Impute from `dim_product.unit_price` (catalog price) | Better than dropping the row or imputing a global mean, which would ignore the product's actual price point. |
| Missing `transport_mode_id` | Impute with that warehouse's most common mode (computed from the data itself) | Avoids a hardcoded default that might not fit the warehouse's actual logistics mix. |
| Inconsistent status casing | Normalize to canonical `Fulfilled`/`Stockout`/`Partial` | Case-insensitive matching would hide the underlying issue rather than fixing it. |
| Extreme quantity outliers | **Flag** (`is_outlier_qty`), never silently drop | Preserves information — an analyst or the forecasting pipeline can choose to exclude flagged rows without losing the record entirely. |

## Stockout risk bands

`config.STOCKOUT_RISK_BANDS = [(0, 0.25, Low), (0.25, 0.5, Medium), (0.5, 0.8, High), (0.8, 1.0, Critical)]`

Chosen as round, business-readable cutoffs rather than derived from the
model's score distribution — a 25%/50%/80% probability of stockout next
week are meaningful, actionable thresholds regardless of exactly how the
model's scores happen to be distributed this run.

## Supplier risk score (rule-based formula)

```
score = (1 - OTIF) * 40
      + min(1, defect_rate) * 300      # defect_rate is a small fraction (e.g. 0.02), so *300 not *40
      + min(1, avg_lead_time_days / 20) * 15
      + min(1, max(0, lead_time_MoM_change)) * 10
      + (10 if single_source else 0)
      + min(1, abs(cost_variance_pct) / 50) * 5
```
Capped at 100. Weights sum to 100 at the theoretical worst case across all
six components; OTIF is weighted heaviest (40) because on-time-in-full
delivery is the single most direct signal of a supplier actually being
able to meet commitments. Full implementation and rationale in
`src/models/supplier_risk_model.py::RULE_WEIGHTS`.

## Business impact assumptions

All figures in `data/processed/business_impact_summary.json` are labeled
**estimated/simulated** and use these documented (not hidden) assumptions
from `config.py`:

| Assumption | Value | Used for |
|---|---|---|
| `STOCKOUT_LOST_MARGIN_RATE` | 0.35 | Margin assumed lost per unit of unmet stockout/partial demand. |
| `HOLDING_COST_RATE_ANNUAL` | 0.22 | Annual cost of carrying inventory, as % of inventory value. |
| Healthy days-of-supply benchmark | The network's own median `days_of_supply` (computed from data, not hardcoded) | Defines "excess" as >2x that benchmark. |
| Recoverable opportunity | 40% of total estimated exposure | Documented assumption that ~40% of total risk exposure is addressable via the recommendation engine's actions; not derived from the data. |

## Recommendation engine thresholds

- SKU recommendations fire only for `risk_band in (High, Critical)` —
  Low/Medium risk doesn't warrant an actionable alert (alert fatigue is a
  real failure mode this deliberately avoids).
- Urgency mapping: Critical → "Immediate", High → "This week", supplier
  Critical → "Immediate", supplier High → "This month" (suppliers move
  slower than SKU replenishment, so a slightly longer response window is
  realistic).
- Excess inventory recommendations fire for `days_of_supply > 15` (roughly
  the top quartile of the observed distribution — see
  `docs/data_dictionary.md`), not an arbitrary round number.
