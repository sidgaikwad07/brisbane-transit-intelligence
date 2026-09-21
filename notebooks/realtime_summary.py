"""Week 2 deliverable: on-time performance and bunching, computed from our
own polled GTFS-Realtime data (not Translink's official stat).

Refreshes the dbt marts (mart_on_time_performance, mart_bunching_by_route,
mart_stop_delay — see dbt/README.md) against whatever raw.trip_updates /
raw.vehicle_positions has accumulated from ingestion/gtfs_realtime_poller.py,
then summarizes them into docs/week2_findings.md + a chart.

This is only as good as the collection window behind it — check the
"Collection window" line in the output doc before trusting the numbers; a
few minutes of polling produces a technically-correct but not-yet-meaningful
report (small samples, whatever happened to be running when you looked).

Usage:
    python notebooks/realtime_summary.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

CHART_PATH = REPO_ROOT / "docs" / "images" / "week2_on_time_by_mode.png"
REPORT_PATH = REPO_ROOT / "docs" / "week2_findings.md"

# "On time" follows the common industry convention: no more than 1 minute
# early, no more than 5 minutes late. Early running is penalised harder
# because it strands passengers who timed their arrival to the schedule.
MIN_SAMPLE_SIZE = 30  # minimum stop-visits for a route to appear in a ranking
MIN_TRIPS = 5  # minimum distinct trips, so one bad/good run can't dominate a route's number

MODE_ORDER = ["Bus", "Rail", "Ferry", "Tram/Light Rail"]
# dataviz skill's validated categorical palette, fixed order (slots 1-4).
MODE_COLORS = {"Bus": "#2a78d6", "Rail": "#eb6834", "Ferry": "#1baf7a", "Tram/Light Rail": "#eda100"}
# Same palette, slots 1-2, reused for the weekday/weekend split.
DAYTYPE_COLORS = {"Weekday": "#2a78d6", "Weekend": "#eb6834"}

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"


def refresh_dbt_marts() -> None:
    import os

    from dotenv import dotenv_values

    env = {**os.environ, **dotenv_values(REPO_ROOT / ".env"), "DBT_PROFILES_DIR": str(DBT_DIR)}
    result = subprocess.run(
        ["dbt", "run"], cwd=DBT_DIR, env=env, capture_output=True, text=True, check=False
    )
    print(result.stdout[-2000:])
    if result.returncode != 0:
        print(result.stderr[-2000:])
        raise RuntimeError("dbt run failed — see output above")


STOP_DELAY_SQL = """
    SELECT
        sd.arrival_delay_sec,
        r.mode,
        -- Saturday/Sunday by the SCHEDULED service date (local time), not by
        -- when we happened to poll it — a stop visit polled late at night
        -- can belong to the next day's early service.
        (extract(dow from sd.scheduled_arrival at time zone 'Australia/Brisbane') in (0, 6)) AS is_weekend
    FROM marts.mart_stop_delay sd
    JOIN staging.stg_routes r ON r.route_id = sd.route_id
    WHERE sd.arrival_delay_sec IS NOT NULL AND sd.scheduled_arrival IS NOT NULL
"""


def fetch_marts(engine) -> dict[str, pd.DataFrame]:
    return {
        "otp": pd.read_sql("SELECT * FROM marts.mart_on_time_performance", engine),
        "bunching": pd.read_sql("SELECT * FROM marts.mart_bunching_by_route", engine),
        "stop_delay": pd.read_sql(STOP_DELAY_SQL, engine),
    }


def collection_window(engine) -> tuple[datetime, datetime, int]:
    row = pd.read_sql(
        "SELECT min(polled_at) AS start, max(polled_at) AS end, count(DISTINCT polled_at) AS n_polls "
        "FROM raw.trip_updates",
        engine,
    ).iloc[0]
    return row["start"], row["end"], int(row["n_polls"])


def citywide_otp(stop_delay: pd.DataFrame) -> dict[str, float]:
    d = stop_delay["arrival_delay_sec"]
    n = len(d)
    if n == 0:
        return {"on_time_pct": float("nan"), "late_pct": float("nan"), "early_pct": float("nan"), "n": 0}
    return {
        "on_time_pct": round(100 * ((d >= -60) & (d <= 300)).sum() / n, 1),
        "late_pct": round(100 * (d > 300).sum() / n, 1),
        "early_pct": round(100 * (d < -60).sum() / n, 1),
        "n": n,
    }


def otp_by_daytype(stop_delay: pd.DataFrame) -> dict[str, dict[str, float]]:
    return {
        "weekday": citywide_otp(stop_delay[~stop_delay["is_weekend"]]),
        "weekend": citywide_otp(stop_delay[stop_delay["is_weekend"]]),
    }


def plot_otp_by_mode_daytype(stop_delay: pd.DataFrame) -> None:
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = stop_delay.copy()
    df["day_type"] = df["is_weekend"].map({False: "Weekday", True: "Weekend"})

    def summarize(g):
        d = g["arrival_delay_sec"]
        return pd.Series({"on_time_pct": 100 * ((d >= -60) & (d <= 300)).sum() / len(d)})

    pivot = (
        df.groupby(["mode", "day_type"])
        .apply(summarize, include_groups=False)
        .reset_index()
        .pivot(index="mode", columns="day_type", values="on_time_pct")
    )
    modes = [m for m in MODE_ORDER if m in pivot.index]
    pivot = pivot.reindex(modes)
    day_types = [d for d in ["Weekday", "Weekend"] if d in pivot.columns]

    x = np.arange(len(modes))
    bar_w = 0.32
    offsets = (np.arange(len(day_types)) - (len(day_types) - 1) / 2) * (bar_w + 0.03)

    fig, ax = plt.subplots(figsize=(8.5, 5.3), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    fig.subplots_adjust(top=0.78, bottom=0.16, left=0.1, right=0.97)

    for day_type, off in zip(day_types, offsets):
        vals = pivot[day_type]
        bars = ax.bar(x + off, vals, width=bar_w, color=DAYTYPE_COLORS[day_type], label=day_type, zorder=3)
        for rect, v in zip(bars, vals):
            if pd.isna(v):
                continue
            ax.text(
                rect.get_x() + rect.get_width() / 2,
                v + 1.5,
                f"{v:.0f}%",
                ha="center",
                fontsize=9,
                fontweight="bold",
                color=INK_PRIMARY,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=10, color=INK_PRIMARY)
    ax.set_ylim(0, 100)
    ax.set_ylabel("On-time stop visits (%)", fontsize=9.5, color=INK_SECONDARY)
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(axis="y", colors=INK_MUTED, labelsize=8.5)
    ax.tick_params(axis="x", length=0, pad=10)
    ax.legend(frameon=False, loc="upper left", fontsize=9.5)

    fig.text(
        0.02,
        0.95,
        "On-time performance by mode — weekday vs weekend",
        fontsize=14,
        fontweight="bold",
        color=INK_PRIMARY,
        va="top",
    )
    fig.text(
        0.02,
        0.885,
        "Measured from our own polled GTFS-Realtime data — not Translink's official stat",
        fontsize=9,
        color=INK_SECONDARY,
        va="top",
    )

    fig.savefig(CHART_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def _format_span(td) -> str:
    total_min = int(td.total_seconds() // 60)
    hours, minutes = divmod(total_min, 60)
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


def write_report(
    otp: pd.DataFrame,
    bunching: pd.DataFrame,
    city: dict[str, float],
    by_daytype: dict[str, dict[str, float]],
    window: tuple[datetime, datetime, int],
) -> None:
    start, end, n_polls = window
    span_td = (end - start) if (start and end) else None
    span = _format_span(span_td) if span_td is not None else "n/a"

    ranked = otp[(otp["n_stop_visits"] >= MIN_SAMPLE_SIZE) & (otp["n_trips"] >= MIN_TRIPS)].sort_values(
        "on_time_pct"
    )
    worst = ranked.head(15)
    best = ranked.sort_values("on_time_pct", ascending=False).head(15)

    lines = [
        "# Week 2 findings — on-time performance & bunching",
        "",
        (
            f"Collection window: **{start:%Y-%m-%d %H:%M} – {end:%Y-%m-%d %H:%M} UTC** "
            f"({span}, {n_polls:,} polls) — our own measurement from polled GTFS-Realtime data, "
            "not Translink's official on-time stat."
        ),
        "",
        (
            "\"On time\" here means arriving no more than 1 minute early and no more than 5 minutes "
            "late — a common industry convention. Early running counts against a route because it "
            "strands passengers who timed their arrival to the published schedule, not just late "
            "running."
        ),
        "",
        "## Citywide",
        "",
        f"- **{city['on_time_pct']}%** of stop visits on time",
        f"- **{city['late_pct']}%** more than 5 minutes late",
        f"- **{city['early_pct']}%** more than 1 minute early",
        f"- {city['n']:,} stop visits measured",
        "",
        "### Weekday vs weekend",
        "",
        (
            "A blended figure across the whole collection window hides a real difference — "
            "**weekday and weekend service run at different reliability**, and earlier versions of "
            "this report were built from weekend-only data without saying so. Split here by the "
            "scheduled service's actual calendar day, not by when we happened to be polling:"
        ),
        "",
        "| | On time | Late | Early | Stop visits |",
        "|---|---|---|---|---|",
        (
            f"| Weekday | {by_daytype['weekday']['on_time_pct']}% | {by_daytype['weekday']['late_pct']}% | "
            f"{by_daytype['weekday']['early_pct']}% | {by_daytype['weekday']['n']:,} |"
        ),
        (
            f"| Weekend | {by_daytype['weekend']['on_time_pct']}% | {by_daytype['weekend']['late_pct']}% | "
            f"{by_daytype['weekend']['early_pct']}% | {by_daytype['weekend']['n']:,} |"
        ),
        "",
        "![On-time performance by mode, weekday vs weekend](images/week2_on_time_by_mode.png)",
        "",
        (
            f"## Worst on-time performance (routes with ≥{MIN_SAMPLE_SIZE} stop visits "
            f"across ≥{MIN_TRIPS} distinct trips)"
        ),
        "",
        "| Route | Mode | On time | Late | Early | Stop visits | Trips |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, row in worst.iterrows():
        name = row["route_short_name"] or row["route_long_name"]
        lines.append(
            f"| {name} | {row['mode']} | {row['on_time_pct']}% | {row['late_pct']}% | "
            f"{row['early_pct']}% | {int(row['n_stop_visits']):,} | {int(row['n_trips'])} |"
        )
    lines += [
        "",
        (
            f"## Best on-time performance (routes with ≥{MIN_SAMPLE_SIZE} stop visits "
            f"across ≥{MIN_TRIPS} distinct trips)"
        ),
        "",
        "| Route | Mode | On time | Late | Early | Stop visits | Trips |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, row in best.iterrows():
        name = row["route_short_name"] or row["route_long_name"]
        lines.append(
            f"| {name} | {row['mode']} | {row['on_time_pct']}% | {row['late_pct']}% | "
            f"{row['early_pct']}% | {int(row['n_stop_visits']):,} | {int(row['n_trips'])} |"
        )

    lines += [
        "",
        "## Bunching (two vehicles on the same route within 400m, same poll)",
        "",
        "| Route | Bunching snapshots | Distinct polls bunched | First seen | Last seen |",
        "|---|---|---|---|---|",
    ]
    for _, row in bunching.head(15).iterrows():
        name = row["route_short_name"] or row["route_long_name"] or row["route_id"]
        lines.append(
            f"| {name} | {int(row['bunching_observations']):,} | {int(row['distinct_polls_bunched']):,} | "
            f"{row['first_seen']:%H:%M} | {row['last_seen']:%H:%M} |"
        )

    lines += [
        "",
        "## Method & caveats",
        "",
        (
            "- **Delay is the last GTFS-RT prediction polled for a stop, not a confirmed arrival "
            "event.** Trip Updates carry predictions that sharpen as a vehicle approaches a stop; "
            "we take the last one polled before the vehicle presumably passed as the closest proxy "
            "to what happened, without cross-referencing vehicle positions stop-by-stop."
        ),
        (
            "- **Bunching is a same-poll, 400m proximity heuristic**, not a same-route-position "
            "check — two vehicles happening to be near each other at a shared terminus or layover "
            "point can register as \"bunched\" without actually being back-to-back on route. Treat "
            "the ranking as directional, not exact."
        ),
        (
            f"- Route rankings only include routes with ≥{MIN_SAMPLE_SIZE} stop visits "
            f"**across ≥{MIN_TRIPS} distinct trips**. Stop visits alone aren't enough: a "
            "low-frequency route can rack up dozens of stop visits from a single catastrophically "
            "delayed trip cascading down its stop sequence, making one bad run look like a "
            "systemically unreliable route. Requiring several independent trips guards against that."
        ),
        (
            "- A short collection window skews toward whatever was running when it was collected "
            "(e.g. all-peak, or all-overnight) — check the collection window above before treating "
            "a route's number as representative of its typical performance."
        ),
        (
            "- The route-level Worst/Best tables and the bunching table below are **blended across "
            "weekday and weekend** (splitting them further would thin out the per-route trip counts "
            "below the reliability threshold for most routes). Only the citywide/mode figures above "
            "are split by day type."
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("Refreshing dbt marts...")
    refresh_dbt_marts()

    engine = create_engine(DATABASE_URL)
    window = collection_window(engine)
    print(f"Collection window: {window[0]} - {window[1]} ({window[2]} polls)")

    marts = fetch_marts(engine)
    city = citywide_otp(marts["stop_delay"])
    print(f"Citywide on-time: {city}")

    by_daytype = otp_by_daytype(marts["stop_delay"])
    print(f"By day type: {by_daytype}")

    plot_otp_by_mode_daytype(marts["stop_delay"])
    print(f"Saved chart to {CHART_PATH}")

    write_report(marts["otp"], marts["bunching"], city, by_daytype, window)
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
