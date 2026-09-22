"""Export the demand-intelligence dbt marts to CSV and a combined XLSX
workbook, for looking at the OD ridership data directly rather than just
the summarized docs/demand_intelligence_findings.md.

Exports land in data/exports/ (gitignored — same treatment as data/raw/).
Assumes the marts are already built (run notebooks/demand_intelligence.py
first, or `dbt run` from dbt/).

Usage:
    python notebooks/export_demand_data.py
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
    "od_demand_by_route": "SELECT * FROM marts.mart_od_demand_by_route ORDER BY total_trips DESC",
    "od_demand_by_time": "SELECT * FROM marts.mart_od_demand_by_time ORDER BY total_trips DESC",
    "od_top_pairs": "SELECT * FROM marts.mart_od_top_pairs ORDER BY total_trips DESC",
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

    xlsx_path = EXPORT_DIR / "demand_data.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for name, df in frames.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)
    print(f"Wrote combined workbook to {xlsx_path}")


if __name__ == "__main__":
    main()
