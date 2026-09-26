"""Regenerate every finding, chart, and export in this repo from whatever
data is currently loaded — the one-command version of what had become a
manual, error-prone ritual of running six-plus scripts in the right order
by hand.

Runs `dbt run` exactly once up front (each script that needs the marts
skips its own internal refresh via SKIP_DBT_REFRESH — see
notebooks/realtime_summary.py / demand_intelligence.py), then runs every
notebooks/*.py script that produces a findings doc or chart, in dependency
order. One script failing doesn't abort the rest — each runs in its own
subprocess, failures are collected and reported at the end, and the exit
code reflects whether anything failed.

Does NOT touch git — regenerates files locally only. Review the diff
(`git status`, `git diff`) and commit yourself; this deliberately stops
short of auto-committing/pushing to a public repo without a look first.

Usage:
    python scripts/refresh_all.py
    python scripts/refresh_all.py --skip-exports   # skip the CSV/XLSX dumps (slower, rarely needed)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

PIPELINE = [
    "notebooks/network_summary.py",
    "notebooks/realtime_summary.py",
    "notebooks/demand_intelligence.py",
    "notebooks/priority_routes.py",
    "notebooks/manly_lota_service_gap.py",
    "notebooks/density_heatmaps.py",
    "notebooks/hero_dashboard.py",
    "notebooks/transit_infographic.py",
]
EXPORT_SCRIPTS = [
    "notebooks/export_week2_data.py",
    "notebooks/export_demand_data.py",
]


def _env() -> dict:
    from dotenv import dotenv_values

    return {**os.environ, **dotenv_values(REPO_ROOT / ".env")}


def run_dbt() -> bool:
    print("=== dbt run (once, shared by every script below) ===")
    env = {**_env(), "DBT_PROFILES_DIR": str(DBT_DIR)}
    result = subprocess.run(["dbt", "run"], cwd=DBT_DIR, env=env, capture_output=True, text=True, check=False)
    print(result.stdout[-1500:])
    if result.returncode != 0:
        print(result.stderr[-1500:])
        print("dbt run FAILED — downstream scripts will likely fail too, continuing anyway")
        return False
    return True


def run_script(rel_path: str) -> tuple[str, bool, float]:
    print(f"\n=== {rel_path} ===")
    python = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    env = {**_env(), "SKIP_DBT_REFRESH": "1"}
    start = time.monotonic()
    result = subprocess.run([python, rel_path], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)
    elapsed = time.monotonic() - start
    print(result.stdout[-1500:])
    ok = result.returncode == 0
    if not ok:
        print(result.stderr[-1500:])
        print(f"FAILED ({elapsed:.0f}s)")
    else:
        print(f"OK ({elapsed:.0f}s)")
    return rel_path, ok, elapsed


def poller_status() -> str:
    check = subprocess.run(
        ["pgrep", "-fl", "ingestion.gtfs_realtime_poller"], capture_output=True, text=True, check=False
    )
    return "running" if check.stdout.strip() else "NOT running"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-exports", action="store_true", help="Skip the CSV/XLSX export scripts")
    args = parser.parse_args()

    results: list[tuple[str, bool, float]] = []

    dbt_ok = run_dbt()
    results.append(("dbt run", dbt_ok, 0.0))

    for script in PIPELINE:
        results.append(run_script(script))

    if not args.skip_exports:
        for script in EXPORT_SCRIPTS:
            results.append(run_script(script))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, ok, elapsed in results:
        status = "OK  " if ok else "FAIL"
        print(f"  [{status}] {name} ({elapsed:.0f}s)" if elapsed else f"  [{status}] {name}")

    n_failed = sum(1 for _, ok, _ in results if not ok)
    total_time = sum(t for _, _, t in results)
    print(f"\n{len(results) - n_failed}/{len(results)} succeeded in {total_time:.0f}s total")
    print(f"GTFS-RT poller: {poller_status()}")
    print("\nNothing was committed — review with `git status`/`git diff` and commit when ready.")

    return 1 if n_failed else 0


if __name__ == "__main__":
    sys.exit(main())
