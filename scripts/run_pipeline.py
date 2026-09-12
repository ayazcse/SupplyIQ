"""
SupplyIQ — Full Pipeline Orchestrator
========================================
Runs the entire project end-to-end, in order:

  1. Generate synthetic dimension tables
  2. Generate synthetic fact tables (simulated demand/inventory dynamics)
  3. Ingest raw + staging data into SQLite
  4. Run data quality validation (prints the DQ score)
  5. Clean/preprocess orders into the trusted warehouse table
  6. Run all 22 SQL analytics queries (validation pass)
  7. Build ML feature panels
  8. Train demand forecasting model
  9. Train stockout risk model
  10. Train supplier risk model
  11. Run anomaly detection
  12. Build the unified risk engine (root-cause evidence)
  13. Calculate business impact
  14. Generate recommendations
  15. Flatten JSON outputs for Power BI
  16. Run the pytest suite

Usage:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --skip-tests      (skip step 16)
    python scripts/run_pipeline.py --quick            (smaller dataset, for a fast smoke test)

Each step is timed and logged. If any step fails, the pipeline stops
immediately and prints which step failed (it does NOT silently continue
with partial/stale data).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

STEPS = [
    ("Generate dimension tables", [PYTHON, "-m", "src.data_generation.generate_dimensions"]),
    ("Generate fact tables (demand/inventory simulation)", [PYTHON, "-m", "src.data_generation.generate_facts"]),
    ("Ingest data into SQLite", [PYTHON, "-m", "src.ingestion.load_raw"]),
    ("Run data quality validation", [PYTHON, "-m", "src.validation.data_quality"]),
    ("Clean & preprocess orders", [PYTHON, "-m", "src.preprocessing.clean_orders"]),
    ("Validate SQL analytics queries", [PYTHON, "scripts/run_sql_queries.py"]),
    ("Build ML feature panels", [PYTHON, "-m", "src.features.build_features"]),
    ("Train demand forecasting model", [PYTHON, "-m", "src.forecasting.demand_forecast"]),
    ("Train stockout risk model", [PYTHON, "-m", "src.models.stockout_risk_model"]),
    ("Train supplier risk model", [PYTHON, "-m", "src.models.supplier_risk_model"]),
    ("Run anomaly detection", [PYTHON, "-m", "src.anomaly_detection.detect_anomalies"]),
    ("Build unified risk engine", [PYTHON, "-m", "src.risk_engine.unified_risk"]),
    ("Calculate business impact", [PYTHON, "-m", "src.risk_engine.business_impact"]),
    ("Generate recommendations", [PYTHON, "-m", "src.recommendations.recommendation_engine"]),
    ("Flatten JSON outputs for Power BI", [PYTHON, "scripts/flatten_json_for_powerbi.py"]),
]

TEST_STEP = ("Run automated test suite", [PYTHON, "-m", "pytest", "tests/", "-v"])


def run_step(name: str, cmd: list[str], step_num: int, total: int) -> float:
    print(f"\n{'='*80}\n[{step_num}/{total}] {name}\n{'='*80}")
    start = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    elapsed = time.time() - start
    if result.returncode != 0:
        print(f"\n❌ STEP FAILED: {name} (exit code {result.returncode}) after {elapsed:.1f}s")
        print("Pipeline stopped. Fix the error above and re-run.")
        sys.exit(result.returncode)
    print(f"✅ Completed in {elapsed:.1f}s")
    return elapsed


def main():
    parser = argparse.ArgumentParser(description="Run the full SupplyIQ pipeline end-to-end.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip the pytest suite at the end")
    args = parser.parse_args()

    steps = list(STEPS)
    if not args.skip_tests:
        steps.append(TEST_STEP)

    print("SupplyIQ — Full Pipeline Run")
    print(f"Root: {ROOT}")
    print(f"Python: {PYTHON}")
    print(f"Total steps: {len(steps)}")

    total_start = time.time()
    timings = []
    for i, (name, cmd) in enumerate(steps, start=1):
        elapsed = run_step(name, cmd, i, len(steps))
        timings.append((name, elapsed))

    total_elapsed = time.time() - total_start
    print(f"\n{'='*80}\nPIPELINE COMPLETE in {total_elapsed:.1f}s\n{'='*80}")
    for name, elapsed in timings:
        print(f"  {elapsed:6.1f}s  {name}")

    print("\nNext steps:")
    print("  - Start the API:        uvicorn src.api.main:app --reload --port 8000")
    print("  - Start the dashboard:  streamlit run app/Home.py")
    print("  - Open Power BI guide:  docs/powerbi.md")


if __name__ == "__main__":
    main()
