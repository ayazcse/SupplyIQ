# Resume Bullets — SupplyIQ

All figures below are drawn from the actual reference pipeline run
documented in this repo (README.md and `data/processed/*.json`), not
rounded up or invented. Adjust wording to match your resume's voice, but
keep the numbers honest to your own run if you regenerate the data.

## ATS-Friendly Version (keyword-dense, 3-4 bullets)

- Built SupplyIQ, an end-to-end supply chain analytics platform processing 170,000+ transactions across SQL (SQLite), Python (Pandas, NumPy, scikit-learn, LightGBM), and Power BI (DAX, star schema), covering data engineering, machine learning, and business intelligence.
- Designed a 14-rule automated data quality engine achieving a 99.9% validation score, and a star-schema data warehouse with 22 advanced SQL queries using window functions, CTEs, and rolling metrics.
- Trained and validated 4 machine learning models (demand forecasting, stockout risk classification, supplier risk scoring, anomaly detection) using proper time-series cross-validation, improving demand forecast accuracy by 7.5% (WAPE) over a seasonal-naive baseline.
- Built a grounded GenAI analyst (retrieval-augmented, LLM-optional) and a rules-based recommendation engine translating model outputs into prioritized business actions, exposed via a FastAPI backend and Streamlit application with 34 passing automated tests.

## Data Analyst Version

- Built a 3-year synthetic supply chain dataset (170K+ orders, 60 suppliers, 120 SKUs) and designed a star-schema SQL data warehouse to support analytical reporting.
- Wrote 22 advanced SQL queries (window functions, rolling averages, CTEs, conditional aggregation) answering real business questions: supplier OTIF ranking, inventory turnover, demand seasonality, and stockout root-cause analysis.
- Built a Power BI dashboard (6 pages, documented DAX measure library) surfacing executive KPIs, supplier risk, and inventory health, backed by a validated, cleaned data pipeline with a 99.9% data quality score.
- Translated model outputs into 150+ prioritized, evidence-backed business recommendations with quantified expected impact.

## Data Scientist Version

- Designed and trained 4 ML models on a realistic simulated supply chain dataset: a LightGBM demand forecaster (beat seasonal-naive baseline by 7.5% WAPE), a stockout-risk classifier (ROC-AUC 0.67 on genuinely stochastic demand), a hybrid rule-based + ML supplier risk scorer (R²=0.86 predicting next-month risk), and an unsupervised anomaly detector (Isolation Forest + rolling z-score).
- Implemented leak-free time-series feature engineering and enforced strict time-based train/test validation throughout, documenting every model's objective, features, validation strategy, and limitations in versioned model cards.
- Built a root-cause analysis engine computing evidence-based explanations directly from before/after data comparisons (not templated text), validated against two deliberately injected ground-truth events (a supplier deterioration and a demand surge).
- Built a retrieval-grounded GenAI layer preventing hallucination by construction: the LLM (or a deterministic local fallback) can only reference pre-computed, retrieved business data.

## BI Analyst Version

- Designed a star-schema data model (7 dimensions, 5 fact tables, 1 bridge table) and built a 6-page Power BI dashboard (Executive Command Center, Demand/Inventory/Supplier/Logistics Intelligence, AI Recommendations) with a documented DAX measure library.
- Automated a 14-rule data quality scoring engine (99.9% score) and a full ETL pipeline (staging → validation → cleaning → warehouse) ensuring dashboard data integrity.
- Built 22 production-style SQL analytics queries covering OTIF, fill rate, inventory turnover, and working-capital exposure, all automatically validated on every pipeline run.
- Delivered a simulated business-impact model quantifying ₹238M in estimated annual supply chain risk exposure across stockouts, excess inventory, and expedited shipping, with fully documented methodology and assumptions.

## Business Analyst Version

- Led the design of SupplyIQ, a supply chain risk intelligence platform answering "what's happening, why, what's next, and what to do" for a simulated mid-size distribution business.
- Built a rules-based decision engine converting 4 machine learning models' outputs into 150+ prioritized, evidence-backed recommendations (issue, evidence, risk, action, expected benefit, urgency).
- Quantified an estimated ₹238M in annual supply chain risk exposure (stockouts, excess inventory, expedited freight) using a documented, assumption-transparent financial model.
- Partnered data engineering, SQL analytics, and machine learning into a single coherent narrative, presented via an executive Power BI dashboard and a natural-language AI analyst for ad hoc business questions.
