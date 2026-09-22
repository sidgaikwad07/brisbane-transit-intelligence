"""One shareable "state of Brisbane transit" dashboard, built for posting
(LinkedIn/GitHub) rather than deep analysis — the headline numbers and
strongest chart from each of the four findings docs this repo has produced,
composed into a single 4:5 portrait image (LinkedIn's best-performing feed
ratio).

Deliberately reuses the pure data-fetching functions from the other
notebooks/*.py scripts rather than recomputing anything — this is a
recomposition of already-verified numbers, not a new analysis. Run the
other four scripts first (or at least once) so the dbt marts it reads are
current.

Usage:
    python notebooks/hero_dashboard.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from demand_intelligence import od_months_covered
from network_summary import fetch_data, pick_weekday_date
from priority_routes import build_priority_table
from realtime_summary import citywide_otp, otp_by_daytype
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

OUT_PATH = REPO_ROOT / "docs" / "images" / "hero_dashboard.png"

MODE_COLORS = {"Bus": "#2a78d6", "Rail": "#eb6834", "Ferry": "#1baf7a", "Tram/Light Rail": "#eda100"}
DAYTYPE_COLORS = {"Weekday": "#2a78d6", "Weekend": "#eb6834"}
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"
ACCENT_RED = "#d03b3b"


def gather(engine) -> dict:
    weekday_date, service_ids = pick_weekday_date(engine)
    stops, routes = fetch_data(engine, service_ids)

    stop_delay = pd.read_sql(
        """
        SELECT sd.arrival_delay_sec, r.mode,
               (extract(dow from sd.scheduled_arrival at time zone 'Australia/Brisbane') in (0, 6))
                   AS is_weekend
        FROM marts.mart_stop_delay sd
        JOIN staging.stg_routes r ON r.route_id = sd.route_id
        WHERE sd.arrival_delay_sec IS NOT NULL AND sd.scheduled_arrival IS NOT NULL
        """,
        engine,
    )
    city_otp = citywide_otp(stop_delay)
    day_otp = otp_by_daytype(stop_delay)

    months = od_months_covered(engine)
    od_total = pd.read_sql("SELECT sum(quantity) AS n FROM raw.od_trips", engine).iloc[0]["n"]

    priority_df, _, _ = build_priority_table(engine)

    window = pd.read_sql(
        "SELECT min(polled_at) AS start, max(polled_at) AS end FROM raw.trip_updates", engine
    ).iloc[0]
    rt_hours = (window["end"] - window["start"]).total_seconds() / 3600

    return {
        "weekday_date": weekday_date,
        "stops": stops,
        "routes": routes,
        "stop_delay": stop_delay,
        "city_otp": city_otp,
        "day_otp": day_otp,
        "months": months,
        "od_total": int(od_total),
        "priority_df": priority_df,
        "rt_hours": rt_hours,
    }


def _stat_tile(ax, value: str, label: str, *, value_color: str = INK_PRIMARY) -> None:
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.text(0.5, 0.62, value, ha="center", va="center", fontsize=22, fontweight="bold", color=value_color)
    ax.text(0.5, 0.22, label, ha="center", va="center", fontsize=9.5, color=INK_SECONDARY, wrap=True)


def plot_priority_mini(ax, df: pd.DataFrame) -> None:
    top = df.head(8)
    med_otp = df["on_time_pct"].median()
    med_demand = df["riders_per_trip"].median()
    ax.axvline(med_otp, color=GRIDLINE, linewidth=1.2, zorder=1)
    ax.axhline(med_demand, color=GRIDLINE, linewidth=1.2, zorder=1)

    for mode, g in df.groupby("mode"):
        ax.scatter(
            g["on_time_pct"], g["riders_per_trip"], s=16, color=MODE_COLORS.get(mode, "#898781"),
            alpha=0.45, linewidths=0, zorder=2,
        )
    for _, row in top.iterrows():
        ax.scatter(
            row["on_time_pct"], row["riders_per_trip"], s=55,
            color=MODE_COLORS.get(row["mode"], "#898781"), edgecolors="white", linewidths=1.1, zorder=4,
        )
    first = top.iloc[0]
    ax.annotate(
        f"{first['route']} — worst combo",
        xy=(first["on_time_pct"], first["riders_per_trip"]),
        xytext=(14, -4),
        textcoords="offset points",
        fontsize=8.5, fontweight="bold", color=ACCENT_RED, va="top",
        arrowprops={"arrowstyle": "-", "color": ACCENT_RED, "lw": 1},
    )

    ax.set_yscale("log")
    ax.set_ylim(top=ax.get_ylim()[1] * 2.2)  # headroom so no point sits under the title
    ax.set_xlabel("On-time performance (%)", fontsize=9, color=INK_SECONDARY)
    ax.set_ylabel("Riders per scheduled trip", fontsize=9, color=INK_SECONDARY)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.spines["left"].set_color(INK_MUTED)
    ax.tick_params(colors=INK_MUTED, labelsize=7.5)
    ax.set_title(
        "Where demand and unreliability overlap", fontsize=11.5, fontweight="bold", color=INK_PRIMARY,
        loc="left", pad=8,
    )


def plot_otp_mini(ax, stop_delay: pd.DataFrame) -> None:
    df = stop_delay.copy()
    df["day_type"] = df["is_weekend"].map({False: "Weekday", True: "Weekend"})

    def summarize(g):
        d = g["arrival_delay_sec"]
        return pd.Series({"on_time_pct": 100 * ((d >= -60) & (d <= 300)).sum() / len(d)})

    mode_order = ["Bus", "Rail", "Ferry", "Tram/Light Rail"]
    pivot = (
        df.groupby(["mode", "day_type"]).apply(summarize, include_groups=False).reset_index()
        .pivot(index="mode", columns="day_type", values="on_time_pct")
    )
    modes = [m for m in mode_order if m in pivot.index]
    pivot = pivot.reindex(modes)
    day_types = [d for d in ["Weekday", "Weekend"] if d in pivot.columns]

    x = np.arange(len(modes))
    bar_w = 0.34
    offsets = (np.arange(len(day_types)) - (len(day_types) - 1) / 2) * (bar_w + 0.03)
    for day_type, off in zip(day_types, offsets):
        vals = pivot[day_type]
        bars = ax.bar(x + off, vals, width=bar_w, color=DAYTYPE_COLORS[day_type], label=day_type, zorder=3)
        for rect, v in zip(bars, vals):
            if pd.isna(v):
                continue
            ax.text(
                rect.get_x() + rect.get_width() / 2, v + 2, f"{v:.0f}", ha="center", fontsize=7.5,
                fontweight="bold", color=INK_PRIMARY,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=8.5, color=INK_PRIMARY)
    ax.set_ylim(0, 118)
    ax.set_ylabel("On-time (%)", fontsize=9, color=INK_SECONDARY)
    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(axis="y", colors=INK_MUTED, labelsize=7.5)
    ax.tick_params(axis="x", length=0)
    ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=7.5, bbox_to_anchor=(0.0, 1.13))
    ax.set_title(
        "Reliability by mode, weekday vs weekend", fontsize=11.5, fontweight="bold", color=INK_PRIMARY,
        loc="left", pad=22,
    )


def build_dashboard(data: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(10, 12.5), dpi=150)
    fig.patch.set_facecolor(SURFACE)

    gs = fig.add_gridspec(
        nrows=3, ncols=4,
        height_ratios=[0.85, 3.7, 2.6],
        hspace=0.6, wspace=0.4,
        left=0.07, right=0.95, top=0.88, bottom=0.08,
    )

    # Header (in the margin above the grid, not a grid row — avoids double-reserving space)
    fig.text(0.07, 0.975, "Brisbane Public Transport: The Real Story", fontsize=22, fontweight="bold",
              color=INK_PRIMARY, va="top")
    fig.text(
        0.07, 0.945,
        "Live GTFS-Realtime polling + Queensland Government's real ridership data — not official stats",
        fontsize=11, color=INK_SECONDARY, va="top",
    )

    # KPI strip — short label text is load-bearing here: each tile is only
    # ~2 inches wide, and matplotlib text isn't clipped to its axes, so a
    # long label bleeds visibly into the neighbouring tile.
    month_span = f"{data['months'][0]:%b}–{data['months'][-1]:%b '%y}"
    kpis = [
        (f"{len(data['stops']):,}", "stops, weekday"),
        (f"{data['city_otp']['on_time_pct']:.0f}%", "on-time citywide"),
        (f"{data['od_total']/1e6:.0f}M+", f"real trips ({month_span})"),
        (data["priority_df"].iloc[0]["route"], "top fix-first route"),
    ]
    for i, (value, label) in enumerate(kpis):
        ax = fig.add_subplot(gs[0, i])
        color = ACCENT_RED if i == 3 else INK_PRIMARY
        _stat_tile(ax, value, label, value_color=color)

    # Hero chart: priority matrix
    ax_hero = fig.add_subplot(gs[1, :])
    plot_priority_mini(ax_hero, data["priority_df"])

    # Secondary row: OTP by mode/daytype, demand by time
    ax_otp = fig.add_subplot(gs[2, :2])
    plot_otp_mini(ax_otp, data["stop_delay"])

    ax_demand = fig.add_subplot(gs[2, 2:])
    top_routes = data["priority_df"].sort_values("avg_weekday_riders", ascending=False).head(8).iloc[::-1]
    colors = [MODE_COLORS.get(m, "#898781") for m in top_routes["mode"]]
    ax_demand.barh(top_routes["route"], top_routes["avg_weekday_riders"], color=colors, height=0.6, zorder=3)
    ax_demand.set_xlabel("Avg weekday riders", fontsize=9, color=INK_SECONDARY)
    ax_demand.grid(axis="x", color=GRIDLINE, linewidth=1, zorder=0)
    ax_demand.set_axisbelow(True)
    for spine in ["top", "right", "left"]:
        ax_demand.spines[spine].set_visible(False)
    ax_demand.spines["bottom"].set_color(INK_MUTED)
    ax_demand.tick_params(axis="x", colors=INK_MUTED, labelsize=7.5)
    ax_demand.tick_params(axis="y", labelsize=8.5, colors=INK_PRIMARY, length=0)
    ax_demand.set_title(
        "Busiest routes, real ridership", fontsize=11.5, fontweight="bold", color=INK_PRIMARY,
        loc="left", pad=8,
    )

    # Footer
    fig.text(
        0.07, 0.018,
        f"Sources: Translink GTFS static + GTFS-Realtime, Queensland Government open data (CC BY 4.0) "
        f"· generated {datetime.now(tz=timezone.utc):%Y-%m-%d} · "
        "github.com/sidgaikwad07/brisbane-transit-intelligence",
        fontsize=7.5, color=INK_MUTED, va="bottom",
    )

    fig.savefig(OUT_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    engine = create_engine(DATABASE_URL)
    data = gather(engine)
    print(f"Weekday date: {data['weekday_date']}, stops={len(data['stops'])}, routes={len(data['routes'])}")
    print(f"Citywide OTP: {data['city_otp']}")
    print(f"OD total: {data['od_total']:,}, months: {[m.isoformat() for m in data['months']]}")
    print(f"Top priority route: {data['priority_df'].iloc[0]['route']}")

    build_dashboard(data)
    print(f"Saved dashboard to {OUT_PATH}")


if __name__ == "__main__":
    main()
