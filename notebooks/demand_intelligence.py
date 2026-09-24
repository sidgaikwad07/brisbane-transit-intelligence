"""Phase 2 deliverable: real passenger demand, from Queensland Government's
aggregated go card/EMV/paper-ticket origin-destination data — not schedule
data used as a demand proxy.

Refreshes the dbt marts (mart_od_demand_by_route, mart_od_demand_by_time,
mart_od_top_pairs — see dbt/README.md) against whatever raw.od_trips has
been loaded by ingestion/od_trips.py, joins actual ridership against
GTFS static's scheduled weekday trip counts (same representative-date
methodology as notebooks/network_summary.py), and writes
docs/demand_intelligence_findings.md + charts.

The headline number this produces that nothing else in this repo can:
**riders per scheduled trip, by route** — a real demand/supply signal, not
just a frequency or on-time-performance proxy for it.

Usage:
    python notebooks/demand_intelligence.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = REPO_ROOT / "dbt"
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL
from ingestion.service_calendar import active_service_ids, representative_dates

TIME_CHART_PATH = REPO_ROOT / "docs" / "images" / "demand_by_time.png"
ROUTE_CHART_PATH = REPO_ROOT / "docs" / "images" / "demand_vs_supply.png"
REPORT_PATH = REPO_ROOT / "docs" / "demand_intelligence_findings.md"

MIN_SCHEDULED_TRIPS = 5  # routes below this are too thin for a riders/trip ratio to mean much

TIME_ORDER = [
    "Weekday (12:00am-8:29:59am)",
    "Weekday (8:30am-2:59:59pm)",
    "Weekday (3:00pm-6:59:59pm)",
    "Weekday (7:00pm-11:59:59pm)",
    "Weekend",
]
TIME_LABELS = {
    "Weekday (12:00am-8:29:59am)": "Weekday\nearly/AM",
    "Weekday (8:30am-2:59:59pm)": "Weekday\nmidday",
    "Weekday (3:00pm-6:59:59pm)": "Weekday\nPM peak",
    "Weekday (7:00pm-11:59:59pm)": "Weekday\nevening",
    "Weekend": "Weekend\n(all day)",
    "Unknown": "Unknown",
}
# dataviz skill's validated categorical palette.
TIME_COLOR = "#2a78d6"
WEEKEND_COLOR = "#eb6834"

INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"


def refresh_dbt_marts() -> None:
    import os

    from dotenv import dotenv_values

    if os.environ.get("SKIP_DBT_REFRESH"):
        # Set by scripts/refresh_all.py, which runs `dbt run` once up front —
        # see the matching guard in notebooks/realtime_summary.py.
        print("Skipping dbt refresh (SKIP_DBT_REFRESH set — already refreshed by the caller)")
        return

    env = {**os.environ, **dotenv_values(REPO_ROOT / ".env"), "DBT_PROFILES_DIR": str(DBT_DIR)}
    result = subprocess.run(["dbt", "run"], cwd=DBT_DIR, env=env, capture_output=True, text=True, check=False)
    print(result.stdout[-2000:])
    if result.returncode != 0:
        print(result.stderr[-2000:])
        raise RuntimeError("dbt run failed — see output above")


def fetch_od_marts(engine) -> dict[str, pd.DataFrame]:
    return {
        "by_route": pd.read_sql("SELECT * FROM marts.mart_od_demand_by_route", engine),
        "by_time": pd.read_sql("SELECT * FROM marts.mart_od_demand_by_time", engine),
        "top_pairs": pd.read_sql("SELECT * FROM marts.mart_od_top_pairs", engine),
    }


def od_months_covered(engine) -> list:
    return sorted(pd.read_sql("SELECT DISTINCT month FROM raw.od_trips ORDER BY month", engine)["month"])


def scheduled_weekday_trips_by_route(engine) -> tuple[pd.DataFrame, object]:
    """Scheduled trips per route_short_name on the representative weekday —
    same date-resolution method as notebooks/network_summary.py, so this is
    directly comparable to that report's numbers.
    """
    calendar = pd.read_sql("SELECT * FROM raw.calendar", engine)
    calendar_dates = pd.read_sql("SELECT * FROM raw.calendar_dates", engine)
    trips_per_service = pd.read_sql(
        "SELECT service_id, count(*) AS n FROM raw.trips GROUP BY service_id", engine
    ).set_index("service_id")["n"]
    weekday_date = representative_dates(calendar, calendar_dates, trips_per_service)["weekday"]
    service_ids = active_service_ids(calendar, calendar_dates, weekday_date)

    df = pd.read_sql(
        """
        SELECT r.route_short_name AS route, count(DISTINCT t.trip_id) AS scheduled_trips
        FROM raw.trips t
        JOIN raw.routes r ON r.route_id = t.route_id
        WHERE t.service_id = ANY(%(service_ids)s) AND r.route_short_name IS NOT NULL
        GROUP BY r.route_short_name
        """,
        engine,
        params={"service_ids": list(service_ids)},
    )
    return df, weekday_date


def count_weekdays(months: list) -> int:
    n = 0
    for m in months:
        span = pd.date_range(m, m + pd.offsets.MonthEnd(0), freq="B")
        n += len(span)
    return n


def plot_demand_by_time(by_time: pd.DataFrame) -> None:
    TIME_CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = by_time.set_index("time_grouping").reindex(TIME_ORDER).dropna(subset=["total_trips"])
    labels = [TIME_LABELS.get(t, t) for t in df.index]
    colors = [WEEKEND_COLOR if t == "Weekend" else TIME_COLOR for t in df.index]

    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    fig.subplots_adjust(top=0.78, bottom=0.16, left=0.13, right=0.97)

    vals = df["total_trips"] / 1e6
    bars = ax.bar(labels, vals, color=colors, width=0.6, zorder=3)
    for rect, v in zip(bars, vals):
        ax.text(
            rect.get_x() + rect.get_width() / 2,
            v + vals.max() * 0.02,
            f"{v:.1f}M",
            ha="center",
            fontsize=10,
            fontweight="bold",
            color=INK_PRIMARY,
        )

    ax.set_ylabel("Trips (millions)", fontsize=9.5, color=INK_SECONDARY)
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(axis="y", colors=INK_MUTED, labelsize=8.5)
    ax.tick_params(axis="x", length=0, labelsize=9.5, colors=INK_PRIMARY)

    fig.text(
        0.02, 0.95, "When Brisbane actually rides transit", fontsize=14, fontweight="bold",
        color=INK_PRIMARY, va="top",
    )
    fig.text(
        0.02,
        0.885,
        "Real go card/EMV/paper-ticket trips, Qld Government open data — not scheduled service",
        fontsize=9,
        color=INK_SECONDARY,
        va="top",
    )

    fig.savefig(TIME_CHART_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def plot_demand_vs_supply(merged: pd.DataFrame) -> None:
    ROUTE_CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    top = merged.sort_values("avg_weekday_riders", ascending=False).head(15).iloc[::-1]

    fig, ax = plt.subplots(figsize=(8.5, 6.5), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    fig.subplots_adjust(top=0.86, bottom=0.08, left=0.1, right=0.96)

    y = np.arange(len(top))
    bars = ax.barh(y, top["avg_weekday_riders"], color=TIME_COLOR, height=0.6, zorder=3)
    for rect, (_, row) in zip(bars, top.iterrows()):
        ax.text(
            rect.get_width() + top["avg_weekday_riders"].max() * 0.01,
            rect.get_y() + rect.get_height() / 2,
            f"{row['avg_weekday_riders']:,.0f} riders/day  ·  {row['riders_per_scheduled_trip']:.0f}/trip",
            va="center",
            fontsize=8,
            color=INK_SECONDARY,
        )

    ax.set_yticks(y)
    ax.set_yticklabels(top["route"], fontsize=9.5, color=INK_PRIMARY)
    ax.set_xlabel("Average weekday riders", fontsize=9.5, color=INK_SECONDARY)
    ax.grid(axis="x", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(axis="x", colors=INK_MUTED, labelsize=8.5)
    ax.tick_params(axis="y", length=0)
    ax.set_xlim(0, top["avg_weekday_riders"].max() * 1.35)

    fig.text(
        0.02, 0.95, "Busiest routes by real ridership", fontsize=14, fontweight="bold",
        color=INK_PRIMARY, va="top",
    )
    fig.text(
        0.02,
        0.905,
        "Average weekday riders (Qld Government OD data) and riders per scheduled trip (vs. GTFS)",
        fontsize=9,
        color=INK_SECONDARY,
        va="top",
    )

    fig.savefig(ROUTE_CHART_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_report(
    months: list,
    by_time: pd.DataFrame,
    top_pairs: pd.DataFrame,
    merged: pd.DataFrame,
    weekday_date,
) -> None:
    month_labels = ", ".join(m.strftime("%B %Y") for m in months)
    total_trips = int(by_time["total_trips"].sum())

    busiest = merged.sort_values("avg_weekday_riders", ascending=False).head(15)
    fullest = merged[merged["scheduled_trips"] >= MIN_SCHEDULED_TRIPS].sort_values(
        "riders_per_scheduled_trip", ascending=False
    ).head(15)
    emptiest = merged[merged["scheduled_trips"] >= MIN_SCHEDULED_TRIPS].sort_values(
        "riders_per_scheduled_trip"
    ).head(15)

    lines = [
        "# Demand intelligence — real ridership from Queensland Government OD data",
        "",
        (
            f"Source: [TransLink Origin-Destination Trips]"
            "(https://www.data.qld.gov.au/dataset/translink-origin-destination-trips-2022-onwards), "
            f"Queensland Government open data (CC BY 4.0) — **{month_labels}** "
            f"({total_trips:,} total trips across the window). Already aggregated by TransLink "
            "(one row per operator/month/route/direction/time-band/ticket-type/origin/destination "
            "with a trip count) — not individual smart-card taps."
        ),
        "",
        "## When people actually ride",
        "",
        "![When Brisbane actually rides transit](images/demand_by_time.png)",
        "",
        "| Time period | Trips | Share |",
        "|---|---|---|",
    ]
    total_for_share = by_time["total_trips"].sum()
    for _, row in by_time.set_index("time_grouping").reindex(TIME_ORDER).dropna(subset=["total_trips"]).reset_index().iterrows():
        label = TIME_LABELS.get(row["time_grouping"], row["time_grouping"])
        lines.append(
            f"| {label.replace(chr(10), ' ')} | {int(row['total_trips']):,} | "
            f"{100 * row['total_trips'] / total_for_share:.1f}% |"
        )

    lines += [
        "",
        "## Real demand vs. scheduled supply, by route",
        "",
        (
            f"Actual average weekday riders per route (from the OD data, divided by "
            f"{{n_weekdays}} weekdays in {month_labels}) against scheduled trips on "
            f"**{weekday_date:%A, %d %B %Y}** (the same representative-weekday methodology as "
            "`docs/week1_findings.md`). `riders_per_scheduled_trip` is the number nothing else in "
            "this repo could produce before now — real demand pressure per scheduled service, not "
            "a frequency or on-time-performance proxy for it."
        ).format(n_weekdays=count_weekdays(months)),
        "",
        "![Busiest routes by real ridership](images/demand_vs_supply.png)",
        "",
        "### Busiest routes overall (by average weekday riders)",
        "",
        "| Route | Mode | Avg weekday riders | Scheduled trips | Riders/trip |",
        "|---|---|---|---|---|",
    ]
    for _, row in busiest.iterrows():
        lines.append(
            f"| {row['route']} | {row['mode'] or '—'} | {row['avg_weekday_riders']:,.0f} | "
            f"{row['scheduled_trips']:.0f} | {row['riders_per_scheduled_trip']:.0f} |"
        )

    lines += [
        "",
        f"### Most demand-pressured (highest riders per scheduled trip, ≥{MIN_SCHEDULED_TRIPS} scheduled trips)",
        "",
        "| Route | Mode | Avg weekday riders | Scheduled trips | Riders/trip |",
        "|---|---|---|---|---|",
    ]
    for _, row in fullest.iterrows():
        lines.append(
            f"| {row['route']} | {row['mode'] or '—'} | {row['avg_weekday_riders']:,.0f} | "
            f"{row['scheduled_trips']:.0f} | {row['riders_per_scheduled_trip']:.0f} |"
        )

    lines += [
        "",
        f"### Least demand-pressured (lowest riders per scheduled trip, ≥{MIN_SCHEDULED_TRIPS} scheduled trips)",
        "",
        "| Route | Mode | Avg weekday riders | Scheduled trips | Riders/trip |",
        "|---|---|---|---|---|",
    ]
    for _, row in emptiest.iterrows():
        lines.append(
            f"| {row['route']} | {row['mode'] or '—'} | {row['avg_weekday_riders']:,.0f} | "
            f"{row['scheduled_trips']:.0f} | {row['riders_per_scheduled_trip']:.0f} |"
        )

    lines += [
        "",
        "## Busiest origin-destination pairs",
        "",
        "| Origin | Destination | Trips (window total) |",
        "|---|---|---|",
    ]
    for _, row in top_pairs.head(15).iterrows():
        o = row["origin_stop_name"] or row["origin_stop"]
        d = row["destination_stop_name"] or row["destination_stop"]
        lines.append(f"| {o} | {d} | {int(row['total_trips']):,} |")

    lines += [
        "",
        "## Method & caveats",
        "",
        (
            "- **This is real ridership**, not a schedule-derived proxy — go card/EMV trips are "
            "counted from an actual touch-on + touch-off pair; paper tickets are counted at "
            "point of issue. See the dataset's own readme for exact definitions."
        ),
        (
            "- `riders_per_scheduled_trip` divides two different-precision things: OD ridership "
            "averaged over a full month (smoothing out day-to-day variation) against scheduled "
            "trips on *one* representative weekday. Treat it as directional — a route-level demand "
            "pressure signal, not a per-trip load figure."
        ),
        (
            "- Route matching is by **route short name** (e.g. \"60\", \"F50\") — the OD data has "
            "no GTFS route_id, and the static feed republishes the same route number across "
            "timetable-version-specific route_id rows, so this is the only reliable join key."
        ),
        "- Weekday count for the daily-average calculation is business days (Mon-Fri); it doesn't subtract public holidays, so the true daily average is a little higher than shown.",
        (
            "- A handful of origin-destination stop pairs don't resolve to a name — those stop "
            "IDs aren't in the current static feed (renumbered or retired since the OD data's "
            "earliest coverage). The trip counts are still real; only the display name is missing."
        ),
        (
            "- **Origin-destination pairs exclude same-stop trips** (origin = destination, ~3.5% "
            "of all trips, ~1.9M over the window) — these cluster heavily at major interchange "
            "stations and most likely represent loop/re-entry journeys rather than point-to-point "
            "travel, so including them would dominate the ranking without answering \"where are "
            "people actually going.\""
        ),
        (
            "- **The OD window (May-Jul 2026) and the GTFS static snapshot (Sept 2026) are "
            "~2 months apart** — a route renumbered, restructured, or discontinued in between "
            "would produce a bogus extreme riders/trip ratio (real historical riders against "
            "wrong or zero current scheduled trips, or vice versa). Treat routes at the extreme "
            "ends of the demand-pressure tables as leads to verify, not settled conclusions, "
            "until cross-checked against a same-period schedule."
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("Refreshing dbt marts...")
    refresh_dbt_marts()

    engine = create_engine(DATABASE_URL)
    months = od_months_covered(engine)
    print(f"OD months loaded: {[m.isoformat() for m in months]}")

    od = fetch_od_marts(engine)
    scheduled, weekday_date = scheduled_weekday_trips_by_route(engine)
    print(f"Representative weekday for scheduled trips: {weekday_date}")

    n_weekdays = count_weekdays(months)
    print(f"Weekdays in window: {n_weekdays}")

    merged = od["by_route"].merge(scheduled, on="route", how="left")
    merged["avg_weekday_riders"] = merged["weekday_trips"] / n_weekdays
    merged["riders_per_scheduled_trip"] = merged["avg_weekday_riders"] / merged["scheduled_trips"]
    merged = merged[merged["scheduled_trips"].notna() & (merged["scheduled_trips"] > 0)]

    plot_demand_by_time(od["by_time"])
    print(f"Saved chart to {TIME_CHART_PATH}")

    plot_demand_vs_supply(merged)
    print(f"Saved chart to {ROUTE_CHART_PATH}")

    write_report(months, od["by_time"], od["top_pairs"], merged, weekday_date)
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
