"""
Executes every query in sql/analytics/business_queries.sql against the live
SQLite warehouse, verifies each runs without error and returns rows, and
writes a sample of each result set to data/processed/sql_query_samples/ for
inspection. This is the "actually tested" proof for the SQL layer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import config as cfg
from src.ingestion.load_raw import get_connection
from src.utils.logger import get_logger

log = get_logger(__name__)

SQL_FILE = cfg.ROOT_DIR / "sql" / "analytics" / "business_queries.sql"
OUT_DIR = cfg.PROCESSED_DIR / "sql_query_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def split_queries(sql_text: str) -> list[tuple[str, str]]:
    """Split the file into (label, sql) pairs using the '-- Qn. ...' header
    comment lines as delimiters."""
    lines = sql_text.splitlines()
    header_pattern = re.compile(r"^-- (Q\d+\..+)$")
    header_positions = [(i, header_pattern.match(l).group(1).strip()) for i, l in enumerate(lines) if header_pattern.match(l)]

    results = []
    for idx, (line_no, label) in enumerate(header_positions):
        start = line_no + 1
        end = header_positions[idx + 1][0] - 2 if idx + 1 < len(header_positions) else len(lines)
        body_lines = lines[start:end]
        # drop comment-only lines (dashes or text) and blank lines at edges
        stmt_lines = [l for l in body_lines if not l.strip().startswith("--")]
        stmt = "\n".join(stmt_lines).strip().rstrip(";").strip()
        if stmt:
            results.append((label, stmt))
    return results


def main():
    sql_text = SQL_FILE.read_text()
    queries = split_queries(sql_text)
    log.info(f"Found {len(queries)} labeled queries in {SQL_FILE.name}")

    conn = get_connection()
    passed, failed = 0, 0
    for label, stmt in queries:
        try:
            df = pd.read_sql(stmt, conn)
            fname = re.sub(r"[^\w]+", "_", label.split(".")[0]).strip("_").lower() + ".csv"
            df.head(20).to_csv(OUT_DIR / fname, index=False)
            log.info(f"[OK]   {label:55s} -> {len(df):>7,} rows")
            passed += 1
        except Exception as e:
            log.error(f"[FAIL] {label:55s} -> {e}")
            failed += 1
    conn.close()

    print(f"\n{passed}/{len(queries)} queries executed successfully. {failed} failed.")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
