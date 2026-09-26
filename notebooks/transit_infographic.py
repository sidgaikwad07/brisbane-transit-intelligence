"""A magazine-style "by the numbers" infographic — icon + big stat + short
caption, the way a university comms team or news outlet would present this
data (think the Monash "public transport" graphic style), rather than a
dense analytical chart. Complements docs/images/hero_dashboard.png, which
is chart-first; this is icon-and-number-first.

Icons are hand-drawn with matplotlib patches (circles/polygons), not an
emoji font — matplotlib's Agg backend can't render color emoji glyphs, and
a missing-glyph "tofu" box would look worse than no icon at all.

Deliberately reuses hero_dashboard.gather() rather than recomputing
anything — this is a recomposition of already-verified numbers.

Usage:
    python notebooks/transit_infographic.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib.pyplot as plt
import pandas as pd
from hero_dashboard import gather
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL

OUT_PATH = REPO_ROOT / "docs" / "images" / "transit_infographic.png"

INK_PRIMARY = "#161311"
INK_SECONDARY = "#514c47"
INK_MUTED = "#8c8579"
SURFACE = "#faf7f2"
CARD_SURFACE = "#ffffff"
ACCENT = "#d0392b"
BADGE_BLUE = "#2a78d6"
BADGE_TEAL = "#1baf7a"
BADGE_AMBER = "#eda100"
BADGE_ORANGE = "#eb6834"
BADGE_RED = "#d0392b"
BADGE_PLUM = "#7d5ba6"


# ── Icons ───────────────────────────────────────────────────────────────
# Every icon function draws into its own 0-1 x 0-1 square axes (aspect
# locked to 'equal' internally), including its own circular badge
# background — that decouples the badge's shape from whatever aspect ratio
# the surrounding grid cell happens to have.


def _badge(ax, color: str) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Circle((0.5, 0.5), 0.48, facecolor=color, linewidth=0, zorder=1))


def icon_bus(ax, color: str) -> None:
    _badge(ax, color)
    ax.add_patch(FancyBboxPatch((0.26, 0.34), 0.48, 0.34, boxstyle="round,pad=0,rounding_size=0.05",
                                 facecolor="white", linewidth=0, zorder=2))
    for x in (0.32, 0.47, 0.62):
        ax.add_patch(Rectangle((x, 0.48), 0.09, 0.12, facecolor=color, linewidth=0, zorder=3))
    for x in (0.35, 0.65):
        ax.add_patch(Circle((x, 0.33), 0.055, facecolor="white", linewidth=0, zorder=3))
        ax.add_patch(Circle((x, 0.33), 0.028, facecolor=color, linewidth=0, zorder=4))


def icon_clock(ax, color: str) -> None:
    _badge(ax, color)
    ax.add_patch(Circle((0.5, 0.5), 0.3, facecolor="none", edgecolor="white", linewidth=4, zorder=2))
    ax.plot([0.5, 0.42], [0.5, 0.64], color="white", linewidth=3.2, solid_capstyle="round", zorder=3)
    ax.plot([0.5, 0.63], [0.5, 0.56], color="white", linewidth=3.2, solid_capstyle="round", zorder=3)


def icon_people(ax, color: str) -> None:
    _badge(ax, color)
    positions = [(0.30, 0.9), (0.5, 1.05), (0.7, 0.9)]
    for cx, scale in positions:
        ax.add_patch(Circle((cx, 0.60 * scale), 0.085 * scale, facecolor="white", linewidth=0, zorder=2))
        ax.add_patch(FancyBboxPatch(
            (cx - 0.11 * scale, 0.26 * scale), 0.22 * scale, 0.24 * scale,
            boxstyle="round,pad=0,rounding_size=0.05", facecolor="white", linewidth=0, zorder=2,
        ))


def icon_pin(ax, color: str) -> None:
    _badge(ax, color)
    ax.add_patch(Polygon([[0.32, 0.55], [0.68, 0.55], [0.5, 0.16]], closed=True, facecolor="white", linewidth=0, zorder=2))
    ax.add_patch(Circle((0.5, 0.62), 0.24, facecolor="white", linewidth=0, zorder=3))
    ax.add_patch(Circle((0.5, 0.62), 0.10, facecolor=color, linewidth=0, zorder=4))


def icon_warning(ax, color: str) -> None:
    _badge(ax, color)
    ax.add_patch(Polygon([[0.5, 0.82], [0.16, 0.22], [0.84, 0.22]], closed=True,
                          facecolor="none", edgecolor="white", linewidth=4.5, joinstyle="round", zorder=2))
    ax.add_patch(Rectangle((0.465, 0.38), 0.07, 0.2, facecolor="white", linewidth=0, zorder=3))
    ax.add_patch(Circle((0.5, 0.30), 0.04, facecolor="white", linewidth=0, zorder=3))


def icon_bunching(ax, color: str) -> None:
    _badge(ax, color)
    ax.add_patch(Circle((0.38, 0.5), 0.24, facecolor="white", alpha=0.9, linewidth=0, zorder=2))
    ax.add_patch(Circle((0.60, 0.5), 0.24, facecolor="white", alpha=0.55, linewidth=0, zorder=3))


def icon_traffic(ax, color: str) -> None:
    _badge(ax, color)
    ax.add_patch(FancyBboxPatch((0.36, 0.16), 0.28, 0.68, boxstyle="round,pad=0,rounding_size=0.06",
                                 facecolor="white", linewidth=0, zorder=2))
    for y, dot_color in zip((0.66, 0.5, 0.34), (BADGE_RED, BADGE_AMBER, BADGE_TEAL)):
        ax.add_patch(Circle((0.5, y), 0.075, facecolor=dot_color, linewidth=0, zorder=3))


def icon_rain(ax, color: str) -> None:
    _badge(ax, color)
    for cx, r in ((0.36, 0.16), (0.52, 0.20), (0.68, 0.15)):
        ax.add_patch(Circle((cx, 0.56), r, facecolor="white", linewidth=0, zorder=2))
    ax.add_patch(Rectangle((0.26, 0.5), 0.48, 0.1, facecolor="white", linewidth=0, zorder=2))
    for x in (0.38, 0.5, 0.62):
        ax.plot([x, x - 0.045], [0.42, 0.24], color="white", linewidth=3, solid_capstyle="round", zorder=3)


# ── Layout ──────────────────────────────────────────────────────────────


def stat_card(fig, cell, icon_fn, badge_color: str, value: str, label: str, value_color: str = INK_PRIMARY) -> None:
    ax = fig.add_subplot(cell)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.02, 0.04), 0.96, 0.92, boxstyle="round,pad=0,rounding_size=0.06",
                                 facecolor=CARD_SURFACE, edgecolor="#eae5db", linewidth=1.2, zorder=1))

    icon_ax = ax.inset_axes([0.09, 0.20, 0.30, 0.60])
    icon_fn(icon_ax, badge_color)

    ax.text(0.47, 0.60, value, fontsize=20, fontweight="bold", color=value_color, va="center", ha="left", zorder=2)
    ax.text(0.47, 0.30, label, fontsize=9.3, color=INK_SECONDARY, va="center", ha="left", wrap=True, zorder=2)


def section_label(fig, x: float, y: float, text: str) -> None:
    fig.text(x, y, text.upper(), fontsize=10.5, fontweight="bold", color=INK_MUTED, va="bottom")
    fig.add_artist(plt.Line2D([x, x + 0.05], [y - 0.008, y - 0.008], color=ACCENT, linewidth=3, transform=fig.transFigure))


def gather_extra(engine) -> dict:
    bunching = pd.read_sql("SELECT COUNT(*) AS n FROM marts.mart_bunching_events", engine).iloc[0]["n"]
    traffic = pd.read_sql(
        """
        WITH latest AS (SELECT MAX(recorded_at) AS t FROM raw.intersection_traffic)
        SELECT AVG(GREATEST(ds1, ds2, ds3, ds4)) AS avg_sat
        FROM raw.intersection_traffic, latest WHERE recorded_at = latest.t
        """,
        engine,
    ).iloc[0]["avg_sat"]
    weather = pd.read_sql(
        "SELECT date, rainfall_mm FROM raw.weather_daily ORDER BY date DESC LIMIT 7", engine
    )
    return {
        "bunching_events": int(bunching),
        "avg_peak_saturation": float(traffic) if traffic is not None else None,
        "rainiest": weather.loc[weather["rainfall_mm"].idxmax()] if not weather.empty else None,
    }


def build_infographic(data: dict, extra: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(9, 12), dpi=150)
    fig.patch.set_facecolor(SURFACE)

    fig.text(0.07, 0.975, "Brisbane Transit,", fontsize=25, fontweight="bold", color=INK_PRIMARY, va="top")
    fig.text(0.07, 0.945, "by the numbers", fontsize=25, fontweight="bold", color=ACCENT, va="top")
    fig.text(
        0.07, 0.905,
        "Live GTFS-Realtime polling + Queensland Government's real ridership data",
        fontsize=11.5, color=INK_SECONDARY, va="top",
    )

    section_label(fig, 0.07, 0.865, "The network, at a glance")
    gs_top = fig.add_gridspec(nrows=1, ncols=3, left=0.06, right=0.96, top=0.85, bottom=0.685, wspace=0.08)
    month_span = f"{data['months'][0]:%b}–{data['months'][-1]:%b '%y}"
    stat_card(fig, gs_top[0, 0], icon_pin, BADGE_BLUE, f"{len(data['stops']):,}", "stops served, weekday")
    stat_card(fig, gs_top[0, 1], icon_bus, BADGE_TEAL, f"{data['city_otp']['n']:,}", "stop visits tracked live")
    stat_card(fig, gs_top[0, 2], icon_people, BADGE_PLUM, f"{data['od_total']/1e6:.0f}M+", f"real rider trips\n({month_span})")

    section_label(fig, 0.07, 0.635, "How it's actually performing")
    gs_mid = fig.add_gridspec(nrows=1, ncols=3, left=0.06, right=0.96, top=0.62, bottom=0.455, wspace=0.08)
    sat = extra["avg_peak_saturation"]
    stat_card(fig, gs_mid[0, 0], icon_clock, BADGE_BLUE, f"{data['city_otp']['on_time_pct']:.0f}%", "on-time,\ncitywide")
    stat_card(fig, gs_mid[0, 1], icon_bunching, BADGE_ORANGE, f"{extra['bunching_events']:,}", "bunching events\nobserved")
    stat_card(
        fig, gs_mid[0, 2], icon_traffic, BADGE_AMBER,
        f"{sat:.0f}%" if sat is not None else "—", "peak intersection\nsaturation, live",
    )

    rainiest = extra["rainiest"]
    if rainiest is not None and rainiest["rainfall_mm"] > 0:
        section_label(fig, 0.07, 0.405, "The other inputs (Week 3)")
        gs_weather = fig.add_gridspec(nrows=1, ncols=1, left=0.06, right=0.375, top=0.39, bottom=0.235)
        stat_card(
            fig, gs_weather[0, 0], icon_rain, BADGE_BLUE,
            f"{rainiest['rainfall_mm']:.1f}mm", f"wettest day this week\n({rainiest['date']:%d %b})",
        )
        spotlight_left, spotlight_top = 0.41, 0.39
    else:
        spotlight_left, spotlight_top = 0.06, 0.405

    # Spotlight: the single call-to-action stat, visually distinct (colored
    # block, not a white card) so it reads as the infographic's punchline.
    top = data["priority_df"].iloc[0]
    gs_spot = fig.add_gridspec(nrows=1, ncols=1, left=spotlight_left, right=0.96, top=spotlight_top, bottom=0.235)
    ax = fig.add_subplot(gs_spot[0, 0])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.0, 0.0), 1.0, 1.0, boxstyle="round,pad=0,rounding_size=0.05",
                                 facecolor=ACCENT, linewidth=0, zorder=1))
    icon_ax = ax.inset_axes([0.05, 0.60, 0.15, 0.32])
    icon_warning(icon_ax, "none")
    icon_ax.patches[0].set_visible(False)  # drop the badge circle; the card itself is already the accent color
    ax.text(0.05, 0.46, "NEEDS ATTENTION FIRST", fontsize=9.5, fontweight="bold", color="#ffe3df", va="top")
    ax.text(0.05, 0.32, f"Route {top['route']}", fontsize=19, fontweight="bold", color="white", va="top")
    ax.text(
        0.05, 0.19,
        f"{top['avg_weekday_riders']:,.0f} riders/weekday · only {top['on_time_pct']:.0f}% on-time",
        fontsize=10.5, fontweight="bold", color="white", va="top",
    )
    ax.text(
        0.05, 0.08,
        f"Busier than {top['demand_pctile']:.0f}% of routes, less reliable than {100 - top['otp_pctile']:.0f}%",
        fontsize=9, color="#ffd9d4", va="top",
    )

    # Runners-up: the spotlight covers #1 in detail, this fills out the
    # picture with #2-4 rather than leaving the page half-empty.
    section_label(fig, 0.07, 0.205, "Also worth watching")
    gs_list = fig.add_gridspec(nrows=1, ncols=1, left=0.06, right=0.96, top=0.188, bottom=0.075)
    ax = fig.add_subplot(gs_list[0, 0])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    runners_up = data["priority_df"].iloc[1:4].reset_index(drop=True)
    n_rows = len(runners_up)
    for i, row in runners_up.iterrows():
        y_top = 1 - i / n_rows
        y = y_top - 0.5 / n_rows
        ax.text(0.0, y, f"#{i + 2}", fontsize=13, fontweight="bold", color=ACCENT, va="center")
        ax.text(0.07, y, f"Route {row['route']}", fontsize=11.5, fontweight="bold", color=INK_PRIMARY, va="center")
        ax.text(0.34, y, row["mode"], fontsize=9, color=INK_MUTED, va="center")
        ax.text(
            0.50, y,
            f"{row['on_time_pct']:.0f}% on-time · {row['avg_weekday_riders']:.0f} riders/weekday",
            fontsize=9.5, color=INK_SECONDARY, va="center",
        )
        if i < n_rows - 1:
            ax.plot([0.0, 1.0], [y_top - 1 / n_rows, y_top - 1 / n_rows], color="#eae5db", linewidth=1)

    fig.text(
        0.07, 0.03,
        f"Sources: Translink GTFS static + GTFS-Realtime, Brisbane City Council open data, "
        f"Queensland Government open data (CC BY 4.0), Open-Meteo · generated "
        f"{datetime.now(tz=timezone.utc):%Y-%m-%d} · github.com/sidgaikwad07/brisbane-transit-intelligence",
        fontsize=7.5, color=INK_MUTED, va="bottom", wrap=True,
    )

    fig.savefig(OUT_PATH, facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    engine = create_engine(DATABASE_URL)
    data = gather(engine)
    extra = gather_extra(engine)
    print(f"OD total: {data['od_total']:,}, bunching events: {extra['bunching_events']:,}")
    print(f"Top priority route: {data['priority_df'].iloc[0]['route']}")

    build_infographic(data, extra)
    print(f"Saved infographic to {OUT_PATH}")


if __name__ == "__main__":
    main()
