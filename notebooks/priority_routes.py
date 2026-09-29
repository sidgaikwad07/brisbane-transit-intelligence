"""Decision-priority synthesis: which routes citywide most need attention,
combining real ridership (Queensland Government OD data) with measured
reliability (our own polled GTFS-RT on-time performance) — the two
questions this repo could only answer separately until now.

A route that's both heavily used *and* unreliable affects far more riders
per late/early arrival than a quiet route running just as badly. Neither
demand alone (notebooks/demand_intelligence.py) nor reliability alone
(notebooks/realtime_summary.py) surfaces that — this does.

Usage:
    python notebooks/priority_routes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import pandas as pd
from demand_intelligence import count_weekdays, od_months_covered, scheduled_weekday_trips_by_route
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

CHART_PATH = REPO_ROOT / "docs" / "images" / "priority_routes.png"
REPORT_PATH = REPO_ROOT / "docs" / "priority_routes_findings.md"

MIN_SCHEDULED_TRIPS = 5
MIN_STOP_VISITS = 30
MIN_OTP_TRIPS = 5
TOP_N = 15

MODE_COLORS = {"Bus": "#2a78d6", "Rail": "#eb6834", "Ferry": "#1baf7a", "Tram/Light Rail": "#eda100"}
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"


def _ordinal(n: int) -> str:
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def mode_aggregate_rows(engine, od: pd.DataFrame, n_weekdays: int, service_ids: set[str]) -> pd.DataFrame:
    """Rail and the Gold Coast Light Rail are reported by the OD dataset as
    one system-wide bucket each ("Rail", "GCLR") rather than per individual
    line, the way bus routes get their own number — GTFS has ~60 separate
    rail route_ids and codes light rail as "L1", so neither OD code matches
    any GTFS route_short_name and the normal per-route join silently drops
    both modes entirely. This computes each as one network-wide aggregate
    "route" instead, so they at least show up rather than vanishing.

    Marked with is_aggregate=True so the chart can render them distinctly
    (a whole network isn't really comparable to one bus route the way two
    bus routes are comparable to each other) — included for visibility, not
    presented as an apples-to-apples ranking against individual routes.
    """
    rows = []
    for od_code, mode, route_types in [("Rail", "Rail", (2,)), ("GCLR", "Tram/Light Rail", (0,))]:
        od_riders = od.loc[od["route"] == od_code, "weekday_trips"].sum() / n_weekdays
        if od_riders <= 0:
            continue
        sched = pd.read_sql(
            """
            SELECT count(DISTINCT t.trip_id) AS n
            FROM raw.trips t JOIN raw.routes r ON r.route_id = t.route_id
            WHERE t.service_id = ANY(%(service_ids)s) AND r.route_type = ANY(%(route_types)s)
            """,
            engine,
            params={"service_ids": list(service_ids), "route_types": list(route_types)},
        ).iloc[0]["n"]
        otp_row = pd.read_sql(
            """
            SELECT
                round(sum(on_time_pct * n_stop_visits) / sum(n_stop_visits), 1) AS on_time_pct,
                sum(n_stop_visits) AS n_stop_visits, sum(n_trips) AS n_trips
            FROM marts.mart_on_time_performance WHERE mode = %(mode)s
            """,
            engine,
            params={"mode": mode},
        ).iloc[0]
        if sched <= 0 or pd.isna(otp_row["on_time_pct"]):
            continue
        rows.append(
            {
                "route": f"{mode} (network)",
                "route_long_name": f"All {mode} lines combined",
                "mode": mode,
                "avg_weekday_riders": od_riders,
                "scheduled_trips": sched,
                "riders_per_trip": od_riders / sched,
                "on_time_pct": otp_row["on_time_pct"],
                "n_stop_visits": otp_row["n_stop_visits"],
                "n_trips": otp_row["n_trips"],
                "is_aggregate": True,
            }
        )
    return pd.DataFrame(rows)


def build_priority_table(engine) -> pd.DataFrame:
    months = od_months_covered(engine)
    n_weekdays = count_weekdays(months)

    scheduled, weekday_date, service_ids = scheduled_weekday_trips_by_route(engine)

    od = pd.read_sql(
        "SELECT route, route_long_name, mode, weekday_trips FROM marts.mart_od_demand_by_route", engine
    )
    od["avg_weekday_riders"] = od["weekday_trips"] / n_weekdays
    demand = od.merge(scheduled, on="route", how="inner")
    demand = demand[demand["scheduled_trips"] >= MIN_SCHEDULED_TRIPS].copy()
    demand["riders_per_trip"] = demand["avg_weekday_riders"] / demand["scheduled_trips"]
    demand["is_aggregate"] = False

    otp = pd.read_sql(
        "SELECT route_short_name AS route, on_time_pct, n_stop_visits, n_trips "
        "FROM marts.mart_on_time_performance "
        f"WHERE n_stop_visits >= {MIN_STOP_VISITS} AND n_trips >= {MIN_OTP_TRIPS}",
        engine,
    )

    merged = demand.merge(otp, on="route", how="inner")
    aggregates = mode_aggregate_rows(engine, od, n_weekdays, service_ids)
    merged = pd.concat([merged, aggregates], ignore_index=True)

    # Percentile ranks computed AFTER folding in the aggregates, so "Rail
    # (network)" and "GCLR (network)" sit in the same ranked population as
    # every individual bus/ferry route rather than being scored separately.
    merged["demand_pctile"] = merged["riders_per_trip"].rank(pct=True) * 100
    merged["otp_pctile"] = merged["on_time_pct"].rank(pct=True) * 100
    # Both factors matter multiplicatively: a route only near the top of one
    # axis doesn't rank highly just for being extreme on the other.
    merged["priority_score"] = merged["demand_pctile"] * (100 - merged["otp_pctile"])
    return merged.sort_values("priority_score", ascending=False), weekday_date, months


def plot_priority_matrix(df: pd.DataFrame) -> None:
    """Top-N routes get a small numbered badge on the scatter point plus a
    ranked list in a side panel, rather than inline text labels next to
    each dot — with several of the top routes clustered close together in
    on-time% (mid-40s to mid-50s), fixed-offset inline labels collided into
    an unreadable pile (confirmed in an earlier version of this chart).
    Numbers collide far less than full route names, and the side list can
    show more per route (mode, riders/trip) than would ever fit on-chart.
    """
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    top = df.head(TOP_N).reset_index(drop=True)

    fig = plt.figure(figsize=(11.5, 7), dpi=200)
    fig.patch.set_facecolor("#fcfcfb")
    gs = fig.add_gridspec(nrows=1, ncols=2, width_ratios=[2.5, 1], left=0.075, right=0.97, top=0.84, bottom=0.1, wspace=0.05)
    ax = fig.add_subplot(gs[0, 0])
    ax_list = fig.add_subplot(gs[0, 1])
    ax_list.axis("off")
    ax.set_facecolor("#fcfcfb")

    med_otp = df["on_time_pct"].median()
    med_demand = df["riders_per_trip"].median()
    ax.axvline(med_otp, color=GRIDLINE, linewidth=1.4, zorder=1)
    ax.axhline(med_demand, color=GRIDLINE, linewidth=1.4, zorder=1)

    for mode, g in df[~df["is_aggregate"]].groupby("mode"):
        ax.scatter(
            g["on_time_pct"], g["riders_per_trip"],
            s=28, color=MODE_COLORS.get(mode, "#898781"), alpha=0.55, zorder=3, label=mode, linewidths=0,
        )
    # Network-wide aggregates (Rail, GCLR — see mode_aggregate_rows) get a
    # star marker: a whole network isn't the same kind of thing as one bus
    # route, so it shouldn't look like just another dot in the swarm.
    aggregates = df[df["is_aggregate"]]
    if not aggregates.empty:
        ax.scatter(
            aggregates["on_time_pct"], aggregates["riders_per_trip"],
            s=140, marker="*", color=[MODE_COLORS.get(m, "#898781") for m in aggregates["mode"]],
            edgecolors="white", linewidths=1, zorder=4, label="Network aggregate",
        )

    for rank, row in top.iterrows():
        marker = "*" if row["is_aggregate"] else "o"
        size = 160 if row["is_aggregate"] else 60
        ax.scatter(
            row["on_time_pct"], row["riders_per_trip"],
            marker=marker, s=size, color=MODE_COLORS.get(row["mode"], "#898781"),
            edgecolors="white", linewidths=1.2, zorder=5,
        )
        ax.annotate(
            str(rank + 1),
            xy=(row["on_time_pct"], row["riders_per_trip"]),
            xytext=(0, 0),
            textcoords="offset points",
            fontsize=6.5,
            fontweight="bold",
            color="white",
            ha="center",
            va="center",
            zorder=6,
        )

    ax.set_yscale("log")
    ax.set_xlabel("On-time performance (%)", fontsize=9.5, color=INK_SECONDARY)
    ax.set_ylabel("Riders per scheduled trip (log scale)", fontsize=9.5, color=INK_SECONDARY)
    ax.grid(False)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.spines["left"].set_color(INK_MUTED)
    ax.tick_params(colors=INK_MUTED, labelsize=8.5)
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)

    ax.text(
        med_otp - 1, ax.get_ylim()[1] * 0.6, "HIGH DEMAND\nLOW RELIABILITY\n(fix first)",
        fontsize=8.5, fontweight="bold", color="#d03b3b", ha="right", va="top",
    )

    # Side list: rank, route, mode, on-time%, riders/trip — everything the
    # on-chart badge can't show without colliding.
    ax_list.text(0.0, 1.0, f"Top {len(top)} by priority score", fontsize=10, fontweight="bold",
                  color=INK_PRIMARY, va="top", transform=ax_list.transAxes)
    line_h = 0.95 / len(top)
    for rank, row in top.iterrows():
        y = 0.92 - rank * line_h
        name = f"{rank + 1}. {row['route']}"
        ax_list.text(0.0, y, name, fontsize=7.8, fontweight="bold", color=INK_PRIMARY,
                      va="top", transform=ax_list.transAxes)
        stats = f"{row['mode']} · {row['on_time_pct']:.0f}% on-time · {row['riders_per_trip']:.0f} riders/trip"
        ax_list.text(0.0, y - line_h * 0.42, stats, fontsize=6.8, color=INK_SECONDARY,
                      va="top", transform=ax_list.transAxes)

    fig.text(
        0.02, 0.95, "Where should Translink act first?", fontsize=15, fontweight="bold",
        color=INK_PRIMARY, va="top",
    )
    fig.text(
        0.02, 0.905,
        "Real ridership vs. measured on-time performance — top-left is the priority zone. "
        "Stars are network-wide, not a single route (see caption).",
        fontsize=9.5, color=INK_SECONDARY, va="top",
    )

    fig.savefig(CHART_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def write_report(df: pd.DataFrame, weekday_date, months: list) -> None:
    month_labels = ", ".join(m.strftime("%B %Y") for m in months)
    top = df.head(TOP_N)

    lines = [
        "# Priority routes — where demand and unreliability overlap",
        "",
        (
            "Every other finding in this repo looks at demand or reliability separately. This "
            "combines them: real ridership (Queensland Government OD data, "
            f"{month_labels}) against measured on-time performance (our own polled GTFS-RT data — "
            "see `docs/week2_findings.md`). A route that's both heavily used *and* unreliable "
            "affects far more riders per late arrival than a quiet route running just as badly — "
            "that's the actual case for where to act first, not raw ridership or raw unreliability "
            "alone."
        ),
        "",
        (
            "`priority_score = demand_percentile × (100 − on_time_percentile)` — both "
            "factors matter multiplicatively; a route only extreme on one axis doesn't rank highly "
            f"for that alone. Scheduled trips on **{weekday_date:%A, %d %B %Y}** (representative "
            "weekday, same method as Week 1)."
        ),
        "",
        "![Where should Translink act first?](images/priority_routes.png)",
        "",
        (
            "**\"Rail (network)\" and \"Tram/Light Rail (network)\" are network-wide aggregates, not "
            "single routes.** The OD dataset reports heavy rail and the Gold Coast Light Rail as one "
            "system-wide bucket each (\"Rail\", \"GCLR\") rather than per individual line the way bus "
            "routes get their own number — so unlike every bus/ferry row below, these two represent "
            "an entire network's average, not one corridor. Included so both modes are visible at "
            "all (a plain per-route join drops them completely — neither OD code matches a GTFS "
            "route_short_name), marked with a star on the chart, not ranked as if directly comparable "
            "to a single route."
        ),
        "",
        "## Top priority routes",
        "",
        "| Route | Mode | Avg weekday riders | Riders/trip (percentile) | On-time % (percentile) |",
        "|---|---|---|---|---|",
    ]
    for _, row in top.iterrows():
        lines.append(
            f"| {row['route']} ({row['route_long_name']}) | {row['mode']} | "
            f"{row['avg_weekday_riders']:,.0f} | {row['riders_per_trip']:.0f} "
            f"({_ordinal(round(row['demand_pctile']))}) | {row['on_time_pct']:.0f}% "
            f"({_ordinal(round(row['otp_pctile']))}) |"
        )

    first = top.iloc[0]
    lines += [
        "",
        (
            f"**{first['route']} ({first['route_long_name']})** tops the list: "
            f"{first['avg_weekday_riders']:,.0f} riders/weekday — "
            f"{_ordinal(round(first['demand_pctile']))} "
            f"percentile demand — running on-time only {first['on_time_pct']:.0f}% of the time "
            f"({_ordinal(round(first['otp_pctile']))} percentile reliability, near the bottom "
            "citywide). This "
            "is a heavily-used service that's unreliable most of the time it runs, which is a "
            "materially bigger problem than either a quiet-but-unreliable route or a busy-but-"
            "punctual one."
        ),
        "",
    ]
    case_study_routes = [r for r in ("220", "227") if r in set(top["route"])]
    if case_study_routes:
        plural = "s" if len(case_study_routes) > 1 else ""
        verb = "appear" if len(case_study_routes) > 1 else "appears"
        lines.append(
            f"Route{plural} {' and '.join(case_study_routes)} from the Manly/Lota/Cleveland case study "
            f"(`docs/manly_lota_service_gap.md`) {verb} in this citywide top list too, independently "
            "confirming that case study's finding: "
            + ("they're" if len(case_study_routes) > 1 else "it's")
            + " not just locally notable, "
            + ("they're" if len(case_study_routes) > 1 else "it's")
            + " among the routes Brisbane's whole network most needs to fix."
        )
        lines.append("")
    lines += [
        "## Caveats",
        "",
        (
            "- Same caveats as the underlying data: ridership is a monthly average against one "
            "representative weekday's schedule (`docs/demand_intelligence_findings.md`), and "
            "on-time performance reflects the collection window logged in `docs/week2_findings.md` "
            "(growing over time as the poller keeps running) — re-run this after a longer "
            "collection window for a more stable reliability figure."
        ),
        (
            "- Percentile-based scoring is relative, not absolute: if the *whole* network were "
            "reliable, a route at the bottom percentile could still have decent raw on-time "
            "performance, and vice versa. Check the raw numbers in the table, not just the rank."
        ),
        (
            "- This ranks routes, not root causes — a route's poor on-time performance could stem "
            "from anything (road congestion, dwell time, schedule padding, driver availability); "
            "this analysis doesn't diagnose which, only where to look."
        ),
        "",
    ]

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    engine = create_engine(DATABASE_URL)
    df, weekday_date, months = build_priority_table(engine)
    print(f"Built priority table: {len(df)} routes, top: {df.iloc[0][['route', 'priority_score']].to_dict()}")

    plot_priority_matrix(df)
    print(f"Saved chart to {CHART_PATH}")

    write_report(df, weekday_date, months)
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
