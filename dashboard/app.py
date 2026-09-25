"""Live Streamlit dashboard for Brisbane Transit Intelligence.

Pulls straight from Postgres — the same dbt marts and raw tables every other
report in this repo is built from — so what you see here is never more than
a few minutes stale, bounded by the poller intervals (GTFS-RT ~60s, traffic
~120s) and the cache TTLs below.

Run it:
    streamlit run dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "notebooks"))

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine

from ingestion.config import DATABASE_URL
from priority_routes import build_priority_table

st.set_page_config(page_title="Brisbane Transit Intelligence", page_icon="🚌", layout="wide")

MODE_COLORS = {"Bus": "#2a78d6", "Rail": "#eb6834", "Ferry": "#1baf7a", "Tram/Light Rail": "#eda100"}
STATUS_COLORS = {"Early": "#2a78d6", "On-time": "#1baf7a", "Late": "#eb6834"}
CACHE_TTL_FAST = 60  # live-ish tables (delays, traffic, vehicle positions)
CACHE_TTL_SLOW = 600  # heavier joins (priority routes, demand)


@st.cache_resource
def get_engine():
    return create_engine(DATABASE_URL)


engine = get_engine()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_collection_window() -> dict:
    df = pd.read_sql("SELECT MIN(polled_at) AS start, MAX(polled_at) AS end FROM raw.trip_updates", engine)
    return df.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_citywide_otp() -> dict:
    df = pd.read_sql(
        """
        SELECT
            ROUND(100.0 * SUM(CASE WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 1 ELSE 0 END) / COUNT(*), 1)
                AS on_time_pct,
            COUNT(*) AS n_stop_visits,
            COUNT(DISTINCT trip_id) AS n_trips
        FROM marts.mart_stop_delay
        """,
        engine,
    )
    return df.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_bunching_summary() -> dict:
    df = pd.read_sql(
        "SELECT COUNT(*) AS n_events, COUNT(DISTINCT route_id) AS n_routes FROM marts.mart_bunching_events", engine
    )
    return df.iloc[0].to_dict()


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_worst_routes(min_trips: int = 5) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT route_short_name AS route, route_long_name, mode, on_time_pct, late_pct, early_pct,
               avg_arrival_delay_sec, n_trips, n_stop_visits
        FROM marts.mart_on_time_performance
        WHERE n_trips >= {min_trips}
        ORDER BY on_time_pct ASC
        LIMIT 15
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_delay_status_breakdown() -> pd.DataFrame:
    """Citywide split of every tracked stop visit into early / on-time / late."""
    df = pd.read_sql(
        """
        SELECT
            SUM(CASE WHEN arrival_delay_sec < -60 THEN 1 ELSE 0 END) AS "Early",
            SUM(CASE WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 1 ELSE 0 END) AS "On-time",
            SUM(CASE WHEN arrival_delay_sec > 300 THEN 1 ELSE 0 END) AS "Late"
        FROM marts.mart_stop_delay
        """,
        engine,
    )
    return df.iloc[0].rename_axis("status").reset_index(name="n_stop_visits")


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_mode_share() -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT mode, SUM(n_trips) AS n_trips, SUM(n_stop_visits) AS n_stop_visits, COUNT(*) AS n_routes
        FROM marts.mart_on_time_performance
        GROUP BY mode
        ORDER BY n_trips DESC
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_otp_by_hour() -> pd.DataFrame:
    """On-time % binned by hour of day (Brisbane local time) — the diurnal
    reliability pattern, aggregated over the whole collection window.
    """
    return pd.read_sql(
        """
        SELECT
            EXTRACT(HOUR FROM last_polled_at AT TIME ZONE 'Australia/Brisbane')::int AS hour,
            ROUND(100.0 * SUM(CASE WHEN arrival_delay_sec BETWEEN -60 AND 300 THEN 1 ELSE 0 END) / COUNT(*), 1)
                AS on_time_pct,
            COUNT(*) AS n_stop_visits
        FROM marts.mart_stop_delay
        GROUP BY 1
        ORDER BY 1
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_traffic_saturation_distribution() -> pd.DataFrame:
    """Every lane's degree-of-saturation reading from the most recent traffic
    poll — the underlying distribution behind the single "peak saturation"
    KPI tile.
    """
    return pd.read_sql(
        """
        WITH latest AS (SELECT MAX(recorded_at) AS t FROM raw.intersection_traffic)
        SELECT GREATEST(ds1, ds2, ds3, ds4) AS peak_saturation
        FROM raw.intersection_traffic, latest
        WHERE recorded_at = latest.t AND GREATEST(ds1, ds2, ds3, ds4) IS NOT NULL
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_bunching_by_route() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT route_short_name AS route, route_long_name, bunching_observations, last_seen "
        "FROM marts.mart_bunching_by_route ORDER BY bunching_observations DESC LIMIT 15",
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_live_delays(minutes: int = 15) -> pd.DataFrame:
    """Arrival delays from the last N minutes of polls — a rolling window
    rather than a single poll, so the histogram has enough points to show a
    real shape (one poll alone is a thin, spiky sample).
    """
    return pd.read_sql(
        f"""
        SELECT tu.route_id, r.route_short_name AS route, r.mode,
               tu.arrival_delay_sec, tu.trip_id, tu.stop_id, tu.polled_at
        FROM raw.trip_updates tu
        JOIN staging.stg_routes r ON r.route_id = tu.route_id
        WHERE tu.polled_at > NOW() - INTERVAL '{minutes} minutes' AND tu.arrival_delay_sec IS NOT NULL
        ORDER BY tu.arrival_delay_sec DESC
        LIMIT 5000
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_traffic_snapshot() -> dict:
    df = pd.read_sql(
        """
        WITH latest AS (SELECT MAX(recorded_at) AS t FROM raw.intersection_traffic)
        SELECT
            recorded_at,
            AVG(GREATEST(ds1, ds2, ds3, ds4)) AS avg_peak_saturation,
            COUNT(DISTINCT tsc) AS n_intersections,
            COUNT(*) AS n_readings
        FROM raw.intersection_traffic, latest
        WHERE recorded_at = latest.t
        GROUP BY recorded_at
        """,
        engine,
    )
    return df.iloc[0].to_dict() if not df.empty else {}


@st.cache_data(ttl=CACHE_TTL_FAST)
def load_traffic_trend(hours: int = 6) -> pd.DataFrame:
    return pd.read_sql(
        f"""
        SELECT
            date_trunc('minute', recorded_at) AS recorded_at,
            AVG(GREATEST(ds1, ds2, ds3, ds4)) AS avg_peak_saturation
        FROM raw.intersection_traffic
        WHERE recorded_at > NOW() - INTERVAL '{hours} hours'
        GROUP BY 1
        ORDER BY 1
        """,
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_weather_recent(days: int = 7) -> pd.DataFrame:
    return pd.read_sql(
        f"SELECT * FROM raw.weather_daily WHERE date > CURRENT_DATE - INTERVAL '{days} days' ORDER BY date",
        engine,
    )


@st.cache_data(ttl=CACHE_TTL_SLOW)
def load_priority_routes() -> pd.DataFrame:
    df, weekday_date, months = build_priority_table(engine)
    return df.head(15)


# ── Header ──────────────────────────────────────────────────────────────

col_title, col_refresh = st.columns([5, 1])
with col_title:
    st.title("🚌 Brisbane Transit Intelligence")
    st.caption(
        "Live from Postgres — GTFS-Realtime, BCC intersection traffic, and daily weather, "
        "all polled continuously. Not a static export."
    )
with col_refresh:
    st.write("")
    if st.button("🔄 Refresh now"):
        st.cache_data.clear()
        st.rerun()

window = load_collection_window()
if window.get("end") is not None:
    age = pd.Timestamp.now(tz="UTC") - window["end"]
    st.caption(
        f"Delay data collected {window['start']:%Y-%m-%d %H:%M} → {window['end']:%Y-%m-%d %H:%M} UTC "
        f"(last poll {age.total_seconds() / 60:.1f} min ago)"
    )

# ── KPI row ─────────────────────────────────────────────────────────────

otp = load_citywide_otp()
bunching = load_bunching_summary()
traffic = load_traffic_snapshot()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Citywide on-time %", f"{otp.get('on_time_pct', 0):.1f}%")
k2.metric("Trips tracked", f"{int(otp.get('n_trips', 0)):,}")
k3.metric("Bunching events", f"{int(bunching.get('n_events', 0)):,}", help="Vehicles <400m apart, same route, same poll")
k4.metric(
    "Peak intersection saturation",
    f"{traffic.get('avg_peak_saturation', 0):.0f}%" if traffic else "—",
    help="Avg of each intersection's busiest lane, most recent poll",
)
k5.metric("Intersections tracked", f"{int(traffic.get('n_intersections', 0)):,}" if traffic else "—")

c1, c2 = st.columns([1, 2])
with c1:
    st.subheader("Delay status, citywide")
    status = load_delay_status_breakdown()
    fig = px.pie(
        status,
        names="status",
        values="n_stop_visits",
        hole=0.55,
        color="status",
        color_discrete_map=STATUS_COLORS,
        category_orders={"status": ["Early", "On-time", "Late"]},
    )
    fig.update_traces(textinfo="percent+label", sort=False)
    total_visits = int(status["n_stop_visits"].sum())
    fig.update_layout(
        height=320,
        margin=dict(t=10, b=10),
        showlegend=False,
        annotations=[dict(text=f"{total_visits:,}<br>stop visits", x=0.5, y=0.5, font_size=14, showarrow=False)],
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption('"On-time" = 1 min early to 5 min late, the common industry convention.')

with c2:
    st.subheader("Trips tracked by mode")
    mode_share = load_mode_share()
    fig = px.bar(
        mode_share,
        x="mode",
        y="n_trips",
        color="mode",
        color_discrete_map=MODE_COLORS,
        text="n_trips",
        labels={"mode": "", "n_trips": "Trips tracked"},
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(height=320, margin=dict(t=10, b=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Distinct trips with at least one polled arrival prediction, this collection window.")

st.divider()

tab_live, tab_reliability, tab_priority, tab_traffic = st.tabs(
    ["🔴 Live delays", "📊 Worst routes & bunching", "🎯 Demand vs reliability", "🚦 Traffic & weather"]
)

# ── Live delays ─────────────────────────────────────────────────────────

with tab_live:
    live = load_live_delays()
    if live.empty:
        st.info("No delay data in the last 15 minutes yet.")
    else:
        as_of = live["polled_at"].max()
        st.caption(
            f"Rolling 15-minute window, most recent poll {as_of:%Y-%m-%d %H:%M:%S} UTC "
            f"— {len(live):,} arrival predictions"
        )

        c1, c2 = st.columns([2, 1])
        with c1:
            fig = px.histogram(
                live,
                x="arrival_delay_sec",
                nbins=60,
                color="mode",
                color_discrete_map=MODE_COLORS,
                labels={"arrival_delay_sec": "Arrival delay (seconds)"},
                title="Arrival delay distribution, last 15 minutes",
            )
            fig.add_vline(x=-60, line_dash="dot", line_color="gray")
            fig.add_vline(x=300, line_dash="dot", line_color="gray")
            fig.update_layout(height=400, margin=dict(t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            # One row per trip: its most recently polled delay, not every
            # poll it appeared in over the window (a trip can be seen 10+
            # times in 15 minutes and shouldn't be counted 10 times).
            latest_per_trip = live.sort_values("polled_at").groupby("trip_id", as_index=False).last()
            worst_now = (
                latest_per_trip[latest_per_trip["arrival_delay_sec"] > 300]
                .groupby("route", as_index=False)["arrival_delay_sec"]
                .agg(n_late_now="count", avg_delay_sec="mean")
                .sort_values("n_late_now", ascending=False)
                .head(10)
            )
            st.markdown("**Routes running late right now** (>5 min)")
            if worst_now.empty:
                st.success("No route currently running more than 5 minutes late.")
            else:
                st.dataframe(worst_now.round(0), hide_index=True, use_container_width=True)

        st.subheader("Reliability by time of day")
        otp_hour = load_otp_by_hour()
        if not otp_hour.empty:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=otp_hour["hour"],
                    y=otp_hour["on_time_pct"],
                    mode="lines+markers",
                    line=dict(color="#2a78d6", width=2.5),
                    marker=dict(size=6),
                    fill="tozeroy",
                    fillcolor="rgba(42,120,214,0.08)",
                )
            )
            fig.update_layout(
                height=320,
                margin=dict(t=10),
                xaxis=dict(title="Hour of day (Brisbane time)", dtick=2, range=[-0.5, 23.5]),
                yaxis=dict(title="On-time %", range=[0, 100]),
            )
            st.plotly_chart(fig, use_container_width=True)
            st.caption(
                "On-time % of all tracked stop visits, binned by hour of day and aggregated across the "
                "whole collection window — shows the diurnal pattern rather than a single day's noise."
            )

# ── Worst routes & bunching ─────────────────────────────────────────────

with tab_reliability:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Least reliable routes")
        worst = load_worst_routes().sort_values("on_time_pct", ascending=False)
        long_names = dict(zip(worst["route"], worst["route_long_name"]))
        melted = worst.melt(
            id_vars=["route"],
            value_vars=["early_pct", "on_time_pct", "late_pct"],
            var_name="status",
            value_name="pct",
        )
        melted["status"] = melted["status"].map(
            {"early_pct": "Early", "on_time_pct": "On-time", "late_pct": "Late"}
        )
        melted["route_long_name"] = melted["route"].map(long_names)
        fig = px.bar(
            melted,
            x="pct",
            y="route",
            color="status",
            orientation="h",
            color_discrete_map=STATUS_COLORS,
            category_orders={"status": ["Early", "On-time", "Late"], "route": worst["route"].tolist()},
            labels={"pct": "Share of stop visits (%)", "route": "Route"},
            hover_data=["route_long_name"],
        )
        fig.update_layout(height=500, margin=dict(t=10), barmode="stack", legend_title=None)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Filtered to routes with ≥5 tracked trips, to avoid one bad run skewing a thin sample.")

    with c2:
        st.subheader("Most bunched routes")
        bunch = load_bunching_by_route()
        if bunch.empty:
            st.info("No bunching detected in the current window.")
        else:
            fig = px.bar(
                bunch.sort_values("bunching_observations"),
                x="bunching_observations",
                y="route",
                orientation="h",
                labels={"bunching_observations": "Bunching observations", "route": "Route"},
                hover_data=["route_long_name"],
            )
            fig.update_traces(marker_color="#eb6834")
            fig.update_layout(height=500, margin=dict(t=10))
            st.plotly_chart(fig, use_container_width=True)
        st.caption("Two vehicles on the same route within 400m in the same poll.")

# ── Demand vs reliability ───────────────────────────────────────────────

with tab_priority:
    st.subheader("Where real demand and poor reliability overlap")
    st.caption(
        "Crosses Queensland Government origin-destination ridership against measured on-time "
        "performance — the routes here affect the most riders per late arrival, citywide."
    )
    priority = load_priority_routes()

    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.scatter(
            priority,
            x="demand_pctile",
            y="otp_pctile",
            size="avg_weekday_riders",
            color="mode",
            color_discrete_map=MODE_COLORS,
            hover_name="route",
            hover_data={"route_long_name": True, "avg_weekday_riders": ":.0f", "on_time_pct": ":.1f"},
            labels={"demand_pctile": "Demand percentile", "otp_pctile": "On-time percentile"},
        )
        fig.update_layout(height=450, margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        top10 = priority.sort_values("priority_score", ascending=False).head(10).iloc[::-1]
        fig = px.bar(
            top10,
            x="priority_score",
            y="route",
            orientation="h",
            color="mode",
            color_discrete_map=MODE_COLORS,
            labels={"priority_score": "Priority score", "route": "Route"},
            hover_data=["route_long_name"],
        )
        fig.update_layout(height=450, margin=dict(t=10), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("demand_pctile × (100 − otp_pctile) — highest first.")

    st.dataframe(
        priority[["route", "route_long_name", "mode", "avg_weekday_riders", "on_time_pct", "priority_score"]].round(1),
        hide_index=True,
        use_container_width=True,
    )

# ── Traffic & weather ────────────────────────────────────────────────────

with tab_traffic:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Intersection congestion trend")
        trend = load_traffic_trend()
        if trend.empty:
            st.info("Traffic poller has just started — trend will fill in over the next few polls.")
        else:
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(x=trend["recorded_at"], y=trend["avg_peak_saturation"], mode="lines", line_color="#2a78d6")
            )
            fig.update_layout(
                height=320,
                margin=dict(t=10),
                yaxis_title="Avg peak-lane saturation (%)",
                xaxis_title=None,
            )
            st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Degree of saturation on each intersection's busiest approach lane, averaged citywide. "
            "The BCC feed is a rolling ~5-minute window with no history, so this trend only covers "
            "time since the poller started."
        )

        st.subheader("Congestion right now, all intersections")
        sat_dist = load_traffic_saturation_distribution()
        if sat_dist.empty:
            st.info("No traffic readings yet.")
        else:
            fig = px.histogram(sat_dist, x="peak_saturation", nbins=40, labels={"peak_saturation": "Peak-lane saturation (%)"})
            fig.update_traces(marker_color="#2a78d6")
            fig.update_layout(height=300, margin=dict(t=10), yaxis_title="Lanes")
            st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{len(sat_dist):,} lane readings from the most recent traffic poll.")

    with c2:
        st.subheader("Recent weather")
        weather = load_weather_recent()
        if weather.empty:
            st.info("No weather data yet — run `python -m ingestion.weather`.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Bar(x=weather["date"], y=weather["rainfall_mm"], name="Rainfall (mm)", marker_color="#2a78d6"))
            fig.add_trace(
                go.Scatter(
                    x=weather["date"], y=weather["temp_max_c"], name="Max temp (°C)", yaxis="y2", line_color="#eb6834"
                )
            )
            fig.update_layout(
                height=350,
                margin=dict(t=10),
                yaxis=dict(title="Rainfall (mm)"),
                yaxis2=dict(title="Max temp (°C)", overlaying="y", side="right"),
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Daily Brisbane observations from Open-Meteo. Feeds the delay-prediction model once "
            "it's built (next step)."
        )

st.divider()
st.caption(
    "Brisbane Transit Intelligence — all data public (Translink GTFS/GTFS-RT, Brisbane City Council "
    "open data, Queensland Government open data, Open-Meteo). Not affiliated with Translink or BCC."
)
