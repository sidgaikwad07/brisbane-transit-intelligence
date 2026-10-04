"""Weekly end-to-end refresh: reload every static dataset, regenerate every
finding, and open a GitHub pull request with the changes for review.

Why weekly, and why static data too: the live pollers keep the real-time
tables current on their own, but everything else goes stale silently —
Translink, Transport for NSW and Transport Victoria republish their
timetables, Sydney Trains only publishes about a month ahead (so without a
reload, the city comparison loses Sydney's rail network within weeks, see
service_calendar.complete_schedule_end), and the OD ridership dataset adds
a month at a time.

Never touches your working copy: everything runs in a separate git worktree
(.worktrees/weekly-refresh) checked out from origin/main on a fresh branch
`data-refresh/<date>`. Only docs/ is committed (every finding, chart and
model card is written there; data/ is gitignored). Never pushes to main —
the result is a pull request for you to review and merge.

Steps, stopping early on anything that would make the results wrong:
  1. Reload static data (Brisbane/Sydney/Melbourne GTFS, OD ridership).
     Any failure stops the run: analysing a half-loaded timetable is worse
     than skipping a week.
  2. scripts/refresh_all.py — dbt + every analysis script. Individual
     script failures don't stop the run; the PR opens as a draft and lists
     them.
  3. Commit docs/, push the branch, open the PR. No changes -> no PR.

A macOS notification reports the outcome. Log: logs/weekly_refresh.log.
Runs Mondays 06:00 as a LaunchAgent (scripts/install_automation.sh).

Usage:
    python scripts/weekly_refresh.py              # full run
    python scripts/weekly_refresh.py --no-pr      # everything except push + PR
    python scripts/weekly_refresh.py --skip-ingest  # reuse current DB data
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.health_check import notify

WORKTREE = REPO_ROOT / ".worktrees" / "weekly-refresh"
VENV_BIN = REPO_ROOT / ".venv" / "bin"
PYTHON = VENV_BIN / "python"
# Gitignored inputs the worktree needs from the main checkout.
SHARED_PATHS = [".env", "data"]

INGEST_STEPS = [
    ("Brisbane GTFS", ["-m", "ingestion.gtfs_static"]),
    ("Sydney GTFS", ["-m", "ingestion.gtfs_static_sydney"]),
    ("Melbourne GTFS", ["-m", "ingestion.gtfs_static_melbourne"]),
    ("OD ridership", ["-m", "ingestion.od_trips"]),
]


def log(msg: str) -> None:
    print(f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": f"{VENV_BIN}:/opt/homebrew/bin:/usr/local/bin:{os.environ.get('PATH', '')}"}
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{result.stderr[-2000:]}")
    return result


def prepare_worktree(branch: str) -> None:
    run(["git", "fetch", "-q", "origin", "main"], cwd=REPO_ROOT)
    if WORKTREE.exists():
        run(["git", "worktree", "remove", "--force", str(WORKTREE)], cwd=REPO_ROOT, check=False)
        shutil.rmtree(WORKTREE, ignore_errors=True)
    run(["git", "worktree", "prune"], cwd=REPO_ROOT)
    run(["git", "worktree", "add", "-q", "-B", branch, str(WORKTREE), "origin/main"], cwd=REPO_ROOT)
    for rel in SHARED_PATHS:
        (WORKTREE / rel).symlink_to(REPO_ROOT / rel)


def cleanup_worktree(branch: str, keep_branch: bool) -> None:
    run(["git", "worktree", "remove", "--force", str(WORKTREE)], cwd=REPO_ROOT, check=False)
    if not keep_branch:
        run(["git", "branch", "-D", branch], cwd=REPO_ROOT, check=False)


def ingest() -> list[tuple[str, bool, float]]:
    results = []
    for name, args in INGEST_STEPS:
        log(f"Loading {name}...")
        start = time.monotonic()
        result = run([str(PYTHON), *args], cwd=WORKTREE, check=False)
        ok = result.returncode == 0
        results.append((name, ok, time.monotonic() - start))
        if not ok:
            log(f"{name} FAILED:\n{result.stderr[-2000:]}")
            break
    return results


def refresh() -> tuple[bool, str]:
    log("Running refresh_all.py...")
    result = run([str(PYTHON), "scripts/refresh_all.py", "--skip-exports"], cwd=WORKTREE, check=False)
    summary = result.stdout[result.stdout.rfind("SUMMARY") :] if "SUMMARY" in result.stdout else result.stdout[-3000:]
    return result.returncode == 0, summary


def pr_body(date: str, ingest_results, refresh_ok: bool, refresh_summary: str, diffstat: str) -> str:
    lines = [
        f"Automated weekly refresh, {date}: static data reloaded and every finding regenerated "
        "(`scripts/weekly_refresh.py`).",
        "",
        "**Review before merging:** check the numbers in the changed docs still make sense. "
        "A big jump usually means a feed changed shape (new route types, a shorter timetable horizon), "
        "not that the network changed overnight.",
        "",
        "## Data reloaded",
        "",
        "| Dataset | Status | Time |",
        "|---|---|---|",
    ]
    lines += [f"| {name} | {'OK' if ok else 'FAILED'} | {secs:.0f}s |" for name, ok, secs in ingest_results]
    lines += [
        "",
        "## Analyses" + ("" if refresh_ok else " (some FAILED, so this PR is a draft)"),
        "",
        "```",
        refresh_summary.strip(),
        "```",
        "",
        "## Changed files",
        "",
        "```",
        diffstat.strip(),
        "```",
        "",
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-pr", action="store_true", help="Don't push or open a PR; leave the worktree for inspection")
    parser.add_argument("--skip-ingest", action="store_true", help="Skip reloading static data")
    args = parser.parse_args()

    date = dt.date.today().isoformat()
    branch = f"data-refresh/{date}"
    log(f"Weekly refresh starting on branch {branch}")
    try:
        prepare_worktree(branch)

        ingest_results = [] if args.skip_ingest else ingest()
        if any(not ok for _, ok, _ in ingest_results):
            failed = next(name for name, ok, _ in ingest_results if not ok)
            notify(f"Weekly refresh stopped: {failed} failed to load. See logs/weekly_refresh.log")
            cleanup_worktree(branch, keep_branch=False)
            return 1

        refresh_ok, refresh_summary = refresh()
        log(refresh_summary)

        run(["git", "add", "-A", "docs"], cwd=WORKTREE)
        if run(["git", "diff", "--cached", "--quiet"], cwd=WORKTREE, check=False).returncode == 0:
            log("No changes to docs/ — nothing to review this week")
            notify("Weekly refresh: no changes this week")
            cleanup_worktree(branch, keep_branch=False)
            return 0 if refresh_ok else 1

        diffstat = run(["git", "diff", "--cached", "--stat"], cwd=WORKTREE).stdout
        if args.no_pr:
            log(f"--no-pr: changes left uncommitted in {WORKTREE}\n{diffstat}")
            return 0 if refresh_ok else 1

        message = f"Weekly data refresh {date}\n\nAutomated by scripts/weekly_refresh.py.\n"
        run(["git", "commit", "-q", "-m", message], cwd=WORKTREE)
        run(["git", "push", "-q", "--force", "-u", "origin", branch], cwd=WORKTREE)
        pr_cmd = [
            "gh", "pr", "create", "--base", "main", "--head", branch,
            "--title", f"Weekly data refresh {date}",
            "--body", pr_body(date, ingest_results, refresh_ok, refresh_summary, diffstat),
        ]
        if not refresh_ok:
            pr_cmd.append("--draft")
        # A second run on the same day force-pushed to the same branch above,
        # which updates its open PR; don't try to open another.
        existing = run(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], cwd=WORKTREE, check=False)
        url = existing.stdout.strip() if existing.returncode == 0 else run(pr_cmd, cwd=WORKTREE).stdout.strip()
        log(f"Opened {url}")
        notify(f"Weekly refresh ready for review: {url}" + ("" if refresh_ok else " (draft: some analyses failed)"))
        cleanup_worktree(branch, keep_branch=True)
        return 0 if refresh_ok else 1
    except Exception as e:
        log(f"Weekly refresh FAILED: {e}")
        notify("Weekly refresh failed. See logs/weekly_refresh.log")
        return 1


if __name__ == "__main__":
    sys.exit(main())
