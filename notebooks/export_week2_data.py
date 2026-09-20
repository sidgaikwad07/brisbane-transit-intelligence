"""Export the Week 2 dbt marts to CSV and a combined XLSX workbook, for
looking at the data directly (Excel/Numbers/Google Sheets) rather than
just the summarized docs/week2_findings.md.

Exports land in data/exports/ (gitignored — these are generated dumps, not
source data, same treatment as data/raw/). Assumes the marts are already
built (run notebooks/realtime_summary.py first, or `dbt run` from dbt/).

Usage:
    python notebooks/export_week2_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

EXPORT_DIR = REPO_ROOT / "data" / "exports"

TABLES = {
    "on_time_performance": "SELECT * FROM marts.mart_on_time_performance ORDER BY n_stop_visits DESC",
    "bunching_by_route": "SELECT * FROM marts.mart_bunching_by_route ORDER BY bunching_observations DESC",
    "stop_delay": "SELECT * FROM marts.mart_stop_delay ORDER BY last_polled_at",
}


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(DATABASE_URL)

    frames = {}
    for name, sql in TABLES.items():
        df = pd.read_sql(sql, engine)
        frames[name] = df
        csv_path = EXPORT_DIR / f"{name}.csv"
        df.to_csv(csv_path, index=False)
        print(f"Wrote {len(df):,} rows to {csv_path}")

    xlsx_path = EXPORT_DIR / "week2_data.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for name, df in frames.items():
            # Excel has no timezone-aware datetime type; drop the (UTC)
            # tzinfo rather than converting to a local zone, so the values
            # printed still match what's in the CSVs and the Postgres columns.
            df = df.copy()
            for col in df.select_dtypes(include=["datetimetz"]).columns:
                df[col] = df[col].dt.tz_localize(None)
            # Excel sheet names cap at 31 chars and stop_delay can run into
            # six figures of rows — well under Excel's ~1.05M row limit, so
            # no truncation needed, just the name.
            df.to_excel(writer, sheet_name=name[:31], index=False)
    print(f"Wrote combined workbook to {xlsx_path}")


if __name__ == "__main__":
    main()
