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
        SELECT route_short_name AS route, route_long_name, mode, on_time_pct, late_pct,
               avg_arrival_delay_sec, n_trips, n_stop_visits
        FROM marts.mart_on_time_performance
        WHERE n_trips >= {min_trips}
        ORDER BY on_time_pct ASC
        LIMIT 15
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
def load_live_delays() -> pd.DataFrame:
    """Most recent poll's arrival delays by route — as live as the poller."""
    return pd.read_sql(
        """
        WITH latest_poll AS (SELECT MAX(polled_at) AS t FROM raw.trip_updates)
        SELECT tu.route_id, r.route_short_name AS route, r.mode,
               tu.arrival_delay_sec, tu.trip_id, tu.stop_id, tu.polled_at
        FROM raw.trip_updates tu
        JOIN staging.stg_routes r ON r.route_id = tu.route_id
        CROSS JOIN latest_poll
        WHERE tu.polled_at = latest_poll.t AND tu.arrival_delay_sec IS NOT NULL
        ORDER BY tu.arrival_delay_sec DESC
        LIMIT 500
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

st.divider()

tab_live, tab_reliability, tab_priority, tab_traffic = st.tabs(
    ["🔴 Live delays", "📊 Worst routes & bunching", "🎯 Demand vs reliability", "🚦 Traffic & weather"]
)

# ── Live delays ─────────────────────────────────────────────────────────

with tab_live:
    live = load_live_delays()
    if live.empty:
        st.info("No delay data in the most recent poll yet.")
    else:
        as_of = live["polled_at"].max()
        st.caption(f"Most recent poll: {as_of:%Y-%m-%d %H:%M:%S} UTC — {len(live)} stop predictions")

        c1, c2 = st.columns([2, 1])
        with c1:
            fig = px.histogram(
                live,
                x="arrival_delay_sec",
                nbins=60,
                color="mode",
                color_discrete_map=MODE_COLORS,
                labels={"arrival_delay_sec": "Arrival delay (seconds)"},
                title="Current arrival delay distribution, all tracked stops",
            )
            fig.add_vline(x=-60, line_dash="dot", line_color="gray")
            fig.add_vline(x=300, line_dash="dot", line_color="gray")
            fig.update_layout(height=400, margin=dict(t=50, b=10))
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            worst_now = (
                live[live["arrival_delay_sec"] > 300]
                .groupby("route", as_index=False)["arrival_delay_sec"]
                .agg(["count", "mean"])
                .reset_index()
                .rename(columns={"count": "n_late_now", "mean": "avg_delay_sec"})
                .sort_values("n_late_now", ascending=False)
                .head(10)
            )
            st.markdown("**Routes running late right now** (>5 min)")
            st.dataframe(worst_now, hide_index=True, use_container_width=True)

# ── Worst routes & bunching ─────────────────────────────────────────────

with tab_reliability:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Least reliable routes")
        worst = load_worst_routes()
        fig = px.bar(
            worst.sort_values("on_time_pct"),
            x="on_time_pct",
            y="route",
            orientation="h",
            color="mode",
            color_discrete_map=MODE_COLORS,
            labels={"on_time_pct": "On-time %", "route": "Route"},
            hover_data=["route_long_name", "n_trips"],
        )
        fig.update_layout(height=500, margin=dict(t=10))
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
    fig.update_layout(height=500, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)
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
                height=350,
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
