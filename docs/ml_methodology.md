# ML Methodology & Model Cards

## Cross-cutting principles

1. **Time-based validation, always.** Every model here is trained on a
   time series (weekly or monthly panels). A random row-level train/test
   split would let the model see rows from the same week as the test set's
   rows, effectively peeking at the future. Every model instead splits by
   calendar time: train on weeks/months up to a percentile cutoff, test on
   everything after.
2. **No label leakage from generation-time truth.** `dim_supplier.archetype`
   (excellent/reliable/average/risky) is the "ground truth" used to *seed*
   the simulation, but it is explicitly excluded from every model's feature
   list. If it were included, the supplier risk model would trivially learn
   to look up the answer instead of learning from OTIF/lead-time/defect
   signals the way a real model would have to.
3. **Report the honest number, not the flattering one.** The stockout
   model's ROC-AUC of 0.67 is reported as-is below, with an explanation of
   why a substantially higher number would actually be suspicious given how
   the demand spikes were generated.

---

## Model Card: Demand Forecasting

- **Objective**: predict next week's order demand (units) per
  product-warehouse pair.
- **Target**: `target_demand_next_week` (from `src/features/build_features.py`)
- **Features**: demand lags (1, 2 weeks), rolling 4/8-week mean and std,
  week-over-week % change, current inventory position, days of supply,
  supplier lead time & volatility & OTIF, defect rate, seasonality flag,
  week-of-year, month, weekly order count.
- **Models compared**: seasonal-naive baseline (4-week rolling average) vs.
  LightGBM gradient boosting.
- **Validation**: time-based split (train ≤ 85th percentile week, test after).
- **Result** (reference run):

  | Model | MAE | RMSE | MAPE % | WAPE % |
  |---|---|---|---|---|
  | Baseline (roll-4-avg) | 588.2 | 4476.8 | 64.4 | 60.9 |
  | LightGBM | 543.9 | 4081.0 | 64.9 | **56.3** |

  LightGBM wins on MAE, RMSE, and WAPE (the primary metric — more robust
  than MAPE when many product-weeks have low/near-zero demand, which
  inflates MAPE's denominator). MAPE is marginally worse for LightGBM,
  which is a known WAPE-vs-MAPE tension on skewed-volume data and is
  reported rather than cherry-picked around.
- **Why the error is this large**: weekly demand noise was deliberately
  generated with a lognormal(σ=0.42) multiplier plus a 5%-per-week chance of
  a 1.5-2.8x organic demand spike (see `docs/data_dictionary.md`) — by
  design, a meaningful share of week-to-week variation is genuinely
  unpredictable from history alone. A WAPE near zero would indicate the
  validation setup was leaking information, not that the model is better.
- **Limitations**: cold-start products with <8 weeks of history fall back
  to the baseline in the app layer; a genuinely novel shock outside the
  training distribution will still cause forecast error; retraining cadence
  is on-demand, not scheduled.

---

## Model Card: Stockout Risk

- **Objective**: P(stockout occurs next week) per product-warehouse pair.
- **Target**: `target_stockout_next_week` (binary).
- **Features**: same lag/rolling demand features as forecasting, plus
  current inventory/days-of-supply and supplier reliability features.
- **Model**: LightGBM classifier, `class_weight="balanced"` (stockouts are
  a ~5% minority class).
- **Validation**: time-based split; metrics chosen for imbalanced
  classification (accuracy would be misleading at ~95% base rate).
- **Result** (reference run): ROC-AUC 0.674, PR-AUC 0.133, Precision 0.099,
  Recall 0.629, F1 0.171.
- **Interpretation**: the model captures real signal (inventory position
  and supplier reliability genuinely predict some stockouts — AUC well
  above the 0.5 random baseline) but is far from perfect, which is expected
  and *desired* here: roughly half of demand variation in this simulation
  is a stochastic weekly spike with no leading indicator in the prior
  week's data. Recall (0.63) is prioritized over precision by the balanced
  class weighting, which fits the business reality that missing a real
  stockout is usually costlier than a false alarm.
- **Limitations**: precision is low (0.099) at the default 0.5 threshold —
  in a real deployment this threshold should be tuned against the actual
  cost ratio of a missed stockout vs. an unnecessary replenishment trigger,
  not left at the default. Cold-start pairs fall back to a rule-based score
  in the risk engine.

---

## Model Card: Supplier Risk

- **Objective**: score every supplier 0-100, two ways:
  1. **Rule-based** (fully transparent, auditable by hand) — weights
     documented in `docs/business_logic.md`.
  2. **Data-driven** — a LightGBM regressor trained to predict *next
     month's* rule-based score from *this month's* leading indicators, so
     it functions as an early-warning smoother on top of the (somewhat
     backward-looking) rule-based number.
- **Features**: OTIF, lead time, defect rate, cost variance, 3-month
  rolling OTIF/lead-time, month-over-month lead-time/OTIF change, order
  volume, single-source flag. (`archetype` excluded — see principle #2 above.)
- **Validation**: time-based split (train ≤ 80th percentile month).
- **Result** (reference run): MAE 4.16 points (on a 0-100 scale), R² 0.857.
- **Validated against the injected shock event**: both suppliers
  deliberately degraded in the simulation (Jul-Sep 2024) show a clear,
  correctly-detected spike — e.g. one supplier's realized lead time moved
  from ~7 to ~13 days and OTIF collapsed from ~0.85 to ~0.30 in the exact
  injected window, and the rule-based risk score spiked from the 20s to the
  50s in lockstep. This was checked directly against `injected_events_log.csv`
  during development, not assumed.
- **Limitations**: the data-driven model predicts the *rule-based* score,
  not an independent ground truth — it's an early-warning smoother, not a
  replacement for the transparent formula.

---

## Model Card: Anomaly Detection

- **Objective**: flag product-warehouse-weeks with unusual demand,
  inventory, or delivery patterns.
- **Methods** (two, each justified rather than stacked for buzzword count):
  1. **Isolation Forest** (multivariate, `contamination=0.03`) — catches
     *combinations* of features that are jointly unusual even if no single
     metric crosses an obvious threshold (e.g., demand up AND inventory
     down AND late orders up simultaneously).
  2. **Rolling z-score** (univariate, per product-warehouse time series,
     window=8, threshold=3σ) — catches a single metric deviating sharply
     from its OWN recent history; more interpretable, and works even for
     series too short for the multivariate model to trust.
- **Result** (reference run): 7.3% of weekly rows flagged, each with a
  stated reason (e.g., "demand z-score=8.0") rather than an opaque score.
- **Limitations**: Isolation Forest's contamination rate (3%) is a
  hyperparameter, not learned — it should be tuned against how many
  anomalies an ops team can realistically triage per week.
