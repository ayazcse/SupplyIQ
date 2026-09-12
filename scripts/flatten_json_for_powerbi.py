"""
Flattens the JSON analytics outputs (which contain nested evidence/driver
lists) into flat CSVs that Power BI's Text/CSV connector can import cleanly.
Run after scripts/run_pipeline.py.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import config as cfg


def flatten(records: list[dict], list_fields: list[str]) -> pd.DataFrame:
    rows = []
    for r in records:
        row = dict(r)
        for f in list_fields:
            if f in row and isinstance(row[f], list):
                if row[f] and isinstance(row[f][0], dict):
                    row[f] = "; ".join(f"{d.get('driver', d)}: {d.get('contribution', '')}" for d in row[f])
                else:
                    row[f] = "; ".join(str(x) for x in row[f])
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    out_dir = cfg.DASHBOARD_EXPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = {
        "recommendations.json": ("recommendations_flat.csv", ["evidence"]),
        "unified_sku_risk.json": ("unified_sku_risk_flat.csv", ["evidence"]),
        "unified_supplier_risk.json": ("unified_supplier_risk_flat.csv", ["evidence"]),
        "supplier_risk_latest.json": ("supplier_risk_latest_flat.csv", ["top_drivers"]),
    }

    for src_name, (out_name, list_fields) in mapping.items():
        src_path = cfg.PROCESSED_DIR / src_name
        if not src_path.exists():
            print(f"SKIP: {src_name} not found (run the pipeline first)")
            continue
        records = json.loads(src_path.read_text())
        df = flatten(records, list_fields)
        df.to_csv(out_dir / out_name, index=False)
        print(f"OK: {out_name} ({len(df)} rows)")


if __name__ == "__main__":
    main()
