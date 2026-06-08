from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "data" / "exports"
DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_LABELS = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}


load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="EV Charging Energy Optimization",
    page_icon="EV",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def get_engine():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://ev_user:ev_password@localhost:5432/ev_charging",
    )
    connect_args = {}
    if database_url.startswith("postgresql"):
        connect_args["connect_timeout"] = 2
    return create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )


def _read_export(filename: str) -> pd.DataFrame:
    path = EXPORT_DIR / filename
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def _exports_ready() -> bool:
    required = [
        "sessions.csv",
        "hourly_site_load.csv",
        "daily_site_metrics.csv",
        "smart_charging_opportunities.csv",
    ]
    return all((EXPORT_DIR / filename).exists() for filename in required)


@st.cache_data(ttl=600, show_spinner=False)
def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    try:
        engine = get_engine()
        with engine.connect() as connection:
            return pd.read_sql_query(text(query), connection, params=params or {})
    except Exception:
        return pd.DataFrame()


def load_filter_options() -> tuple[list[str], pd.Timestamp | None, pd.Timestamp | None]:
    if _exports_ready():
        sessions = _read_export("sessions.csv")
        if not sessions.empty:
            sessions["connection_date"] = pd.to_datetime(sessions["connection_date"])
            return (
                sorted(sessions["site_id"].dropna().unique().tolist()),
                sessions["connection_date"].min(),
                sessions["connection_date"].max(),
            )

    df = read_sql(
        """
        SELECT
            site_id,
            MIN(connection_date)::TEXT AS min_date,
            MAX(connection_date)::TEXT AS max_date
        FROM fact_charging_session
        GROUP BY site_id
        ORDER BY site_id
        """
    )
    if df.empty:
        sessions = _read_export("sessions.csv")
        if sessions.empty:
            return [], None, None
        sessions["connection_date"] = pd.to_datetime(sessions["connection_date"])
        return (
            sorted(sessions["site_id"].dropna().unique().tolist()),
            sessions["connection_date"].min(),
            sessions["connection_date"].max(),
        )

    min_date = pd.to_datetime(df["min_date"]).min()
    max_date = pd.to_datetime(df["max_date"]).max()
    return sorted(df["site_id"].dropna().unique().tolist()), min_date, max_date


def db_available() -> bool:
    if _exports_ready():
        return False
    probe = read_sql("SELECT 1 AS ok")
    return not probe.empty


def query_kpis(site_id: str, start_date, end_date) -> pd.DataFrame:
    if _exports_ready():
        sessions = _read_export("sessions.csv")
        if sessions.empty:
            return pd.DataFrame()
        sessions["connection_date"] = pd.to_datetime(sessions["connection_date"]).dt.date
        mask = (
            (sessions["site_id"] == site_id)
            & (sessions["connection_date"] >= start_date)
            & (sessions["connection_date"] <= end_date)
        )
        filtered = sessions.loc[mask]
        return pd.DataFrame(
            [
                {
                    "sessions": len(filtered),
                    "stations": filtered["station_id"].nunique(),
                    "total_kwh": filtered["kwh_delivered"].sum(),
                    "avg_kwh_per_session": filtered["kwh_delivered"].mean(),
                    "avg_duration_hr": filtered["session_duration_min"].mean() / 60.0,
                    "avg_idle_hr": filtered["idle_duration_min"].mean() / 60.0,
                }
            ]
        )

    df = read_sql(
        """
        SELECT
            COUNT(*) AS sessions,
            COUNT(DISTINCT station_id) AS stations,
            SUM(kwh_delivered) AS total_kwh,
            AVG(kwh_delivered) AS avg_kwh_per_session,
            AVG(session_duration_min) / 60.0 AS avg_duration_hr,
            AVG(idle_duration_min) / 60.0 AS avg_idle_hr
        FROM fact_charging_session
        WHERE site_id = :site_id
          AND connection_date BETWEEN :start_date AND :end_date
        """,
        {"site_id": site_id, "start_date": str(start_date), "end_date": str(end_date)},
    )
    if not df.empty:
        return df

    sessions = _read_export("sessions.csv")
    if sessions.empty:
        return pd.DataFrame()
    sessions["connection_date"] = pd.to_datetime(sessions["connection_date"]).dt.date
    mask = (
        (sessions["site_id"] == site_id)
        & (sessions["connection_date"] >= start_date)
        & (sessions["connection_date"] <= end_date)
    )
    filtered = sessions.loc[mask]
    return pd.DataFrame(
        [
            {
                "sessions": len(filtered),
                "stations": filtered["station_id"].nunique(),
                "total_kwh": filtered["kwh_delivered"].sum(),
                "avg_kwh_per_session": filtered["kwh_delivered"].mean(),
                "avg_duration_hr": filtered["session_duration_min"].mean() / 60.0,
                "avg_idle_hr": filtered["idle_duration_min"].mean() / 60.0,
            }
        ]
    )


def query_heatmap(site_id: str, start_date, end_date) -> pd.DataFrame:
    if _exports_ready():
        hourly = _read_export("hourly_site_load.csv")
        if hourly.empty:
            return pd.DataFrame()
        hourly["hour_bucket_local"] = pd.to_datetime(hourly["hour_bucket_local"])
        mask = (
            (hourly["site_id"] == site_id)
            & (hourly["hour_bucket_local"].dt.date >= start_date)
            & (hourly["hour_bucket_local"].dt.date <= end_date)
        )
        df = (
            hourly.loc[mask]
            .groupby(["local_isodow", "local_hour"], as_index=False)["estimated_kwh"]
            .sum()
            .rename(columns={"estimated_kwh": "total_kwh"})
        )
        df["day"] = df["local_isodow"].map(DAY_LABELS)
        return df

    df = read_sql(
        """
        SELECT
            local_isodow,
            local_hour,
            SUM(estimated_kwh) AS total_kwh
        FROM mv_hourly_site_load
        WHERE site_id = :site_id
          AND hour_bucket_local::DATE BETWEEN :start_date AND :end_date
        GROUP BY local_isodow, local_hour
        ORDER BY local_isodow, local_hour
        """,
        {"site_id": site_id, "start_date": str(start_date), "end_date": str(end_date)},
    )
    if df.empty:
        hourly = _read_export("hourly_site_load.csv")
        if hourly.empty:
            return pd.DataFrame()
        hourly["hour_bucket_local"] = pd.to_datetime(hourly["hour_bucket_local"])
        mask = (
            (hourly["site_id"] == site_id)
            & (hourly["hour_bucket_local"].dt.date >= start_date)
            & (hourly["hour_bucket_local"].dt.date <= end_date)
        )
        df = (
            hourly.loc[mask]
            .groupby(["local_isodow", "local_hour"], as_index=False)["estimated_kwh"]
            .sum()
            .rename(columns={"estimated_kwh": "total_kwh"})
        )
    df["day"] = df["local_isodow"].map(DAY_LABELS)
    return df


def query_daily(site_id: str, start_date, end_date) -> pd.DataFrame:
    if _exports_ready():
        df = _read_export("daily_site_metrics.csv")
        if df.empty:
            return df
        df["metric_date"] = pd.to_datetime(df["metric_date"]).dt.date
        df = df[
            (df["site_id"] == site_id)
            & (df["metric_date"] >= start_date)
            & (df["metric_date"] <= end_date)
        ].sort_values("metric_date")
        df["metric_date"] = pd.to_datetime(df["metric_date"])
        return df

    df = read_sql(
        """
        SELECT
            metric_date,
            session_count,
            total_kwh,
            utilization_rate,
            rolling_7d_utilization,
            rolling_7d_kwh
        FROM mv_daily_site_metrics
        WHERE site_id = :site_id
          AND metric_date BETWEEN :start_date AND :end_date
        ORDER BY metric_date
        """,
        {"site_id": site_id, "start_date": str(start_date), "end_date": str(end_date)},
    )
    if df.empty:
        df = _read_export("daily_site_metrics.csv")
        if df.empty:
            return df
        df["metric_date"] = pd.to_datetime(df["metric_date"]).dt.date
        df = df[
            (df["site_id"] == site_id)
            & (df["metric_date"] >= start_date)
            & (df["metric_date"] <= end_date)
        ].sort_values("metric_date")
    df["metric_date"] = pd.to_datetime(df["metric_date"])
    return df


def query_load_curve(site_id: str, start_date, end_date) -> pd.DataFrame:
    if _exports_ready():
        hourly = _read_export("hourly_site_load.csv")
        if hourly.empty:
            return pd.DataFrame()
        hourly["hour_bucket_local"] = pd.to_datetime(hourly["hour_bucket_local"])
        mask = (
            (hourly["site_id"] == site_id)
            & (hourly["hour_bucket_local"].dt.date >= start_date)
            & (hourly["hour_bucket_local"].dt.date <= end_date)
        )
        return (
            hourly.loc[mask]
            .groupby("local_hour", as_index=False)["estimated_avg_kw"]
            .agg(avg_kw="mean", p95_kw=lambda x: x.quantile(0.95))
        )

    df = read_sql(
        """
        SELECT
            local_hour,
            AVG(estimated_avg_kw) AS avg_kw,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY estimated_avg_kw) AS p95_kw
        FROM mv_hourly_site_load
        WHERE site_id = :site_id
          AND hour_bucket_local::DATE BETWEEN :start_date AND :end_date
        GROUP BY local_hour
        ORDER BY local_hour
        """,
        {"site_id": site_id, "start_date": str(start_date), "end_date": str(end_date)},
    )
    if not df.empty:
        return df

    hourly = _read_export("hourly_site_load.csv")
    if hourly.empty:
        return pd.DataFrame()
    hourly["hour_bucket_local"] = pd.to_datetime(hourly["hour_bucket_local"])
    mask = (
        (hourly["site_id"] == site_id)
        & (hourly["hour_bucket_local"].dt.date >= start_date)
        & (hourly["hour_bucket_local"].dt.date <= end_date)
    )
    return (
        hourly.loc[mask]
        .groupby("local_hour", as_index=False)["estimated_avg_kw"]
        .agg(avg_kw="mean", p95_kw=lambda x: x.quantile(0.95))
    )


def query_storage(site_id: str, start_date, end_date) -> pd.DataFrame:
    if _exports_ready():
        storage = _read_export("smart_charging_opportunities.csv")
        if storage.empty:
            return pd.DataFrame()
        storage["connection_time"] = pd.to_datetime(storage["connection_time"])
        mask = (
            (storage["site_id"] == site_id)
            & (storage["connection_time"].dt.date >= start_date)
            & (storage["connection_time"].dt.date <= end_date)
        )
        storage = storage.loc[mask].copy()
        storage["month_start"] = storage["connection_time"].dt.to_period("M").dt.to_timestamp()
        return (
            storage.groupby("month_start", as_index=False)
            .agg(
                shiftable_kwh=("shiftable_kwh", "sum"),
                savings_usd=("estimated_energy_cost_savings_usd", "sum"),
                flexible_sessions=("shiftable_kwh", lambda x: int((x > 0).sum())),
            )
            .sort_values("month_start")
        )

    df = read_sql(
        """
        SELECT
            date_trunc('month', connection_time)::DATE AS month_start,
            SUM(shiftable_kwh) AS shiftable_kwh,
            SUM(estimated_energy_cost_savings_usd) AS savings_usd,
            COUNT(*) FILTER (WHERE shiftable_kwh > 0) AS flexible_sessions
        FROM mv_smart_charging_opportunities
        WHERE site_id = :site_id
          AND connection_time::DATE BETWEEN :start_date AND :end_date
        GROUP BY date_trunc('month', connection_time)
        ORDER BY month_start
        """,
        {"site_id": site_id, "start_date": str(start_date), "end_date": str(end_date)},
    )
    if not df.empty:
        df["month_start"] = pd.to_datetime(df["month_start"])
        return df

    storage = _read_export("smart_charging_opportunities.csv")
    if storage.empty:
        return pd.DataFrame()
    storage["connection_time"] = pd.to_datetime(storage["connection_time"])
    mask = (
        (storage["site_id"] == site_id)
        & (storage["connection_time"].dt.date >= start_date)
        & (storage["connection_time"].dt.date <= end_date)
    )
    storage = storage.loc[mask].copy()
    storage["month_start"] = storage["connection_time"].dt.to_period("M").dt.to_timestamp()
    return (
        storage.groupby("month_start", as_index=False)
        .agg(
            shiftable_kwh=("shiftable_kwh", "sum"),
            savings_usd=("estimated_energy_cost_savings_usd", "sum"),
            flexible_sessions=("shiftable_kwh", lambda x: int((x > 0).sum())),
        )
        .sort_values("month_start")
    )


st.title("EV Charging Energy Optimization")

sites, min_date, max_date = load_filter_options()
if not sites or min_date is None or max_date is None:
    st.info("No loaded charging data found. Run the ELT pipeline, then refresh this page.")
    st.code(
        "docker compose up -d\n"
        "python -m ev_charging_analytics.pipeline --skip-extract --raw-json data/raw/acn_sessions_caltech.json",
        language="bash",
    )
    st.stop()

with st.sidebar:
    st.header("Filters")
    selected_site = st.selectbox("Site", sites)
    start_date, end_date = st.date_input(
        "Date range",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date(),
    )
    source_label = "PostgreSQL" if db_available() else "CSV exports"
    st.caption(f"Source: {source_label}")

kpis = query_kpis(selected_site, start_date, end_date)
if kpis.empty:
    st.warning("No sessions matched the selected filters.")
    st.stop()

kpi = kpis.iloc[0].fillna(0)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Sessions", f"{int(kpi['sessions']):,}")
col2.metric("Stations", f"{int(kpi['stations']):,}")
col3.metric("Energy", f"{kpi['total_kwh']:,.0f} kWh")
col4.metric("Avg Session", f"{kpi['avg_duration_hr']:.1f} hr")
col5.metric("Avg Idle", f"{kpi['avg_idle_hr']:.1f} hr")

heatmap = query_heatmap(selected_site, start_date, end_date)
daily = query_daily(selected_site, start_date, end_date)
load_curve = query_load_curve(selected_site, start_date, end_date)
storage = query_storage(selected_site, start_date, end_date)

left, right = st.columns([1.1, 0.9])
with left:
    if not heatmap.empty:
        matrix = (
            heatmap.pivot_table(
                index="day", columns="local_hour", values="total_kwh", aggfunc="sum"
            )
            .reindex(DAY_ORDER)
            .fillna(0)
        )
        fig = px.imshow(
            matrix,
            aspect="auto",
            color_continuous_scale="Viridis",
            labels={"x": "Hour", "y": "Day", "color": "kWh"},
            title="Energy Consumption Heatmap",
        )
        fig.update_layout(height=430, margin=dict(l=20, r=20, t=60, b=20))
        st.plotly_chart(fig, use_container_width=True)

with right:
    if not load_curve.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=load_curve["local_hour"],
                y=load_curve["avg_kw"],
                mode="lines+markers",
                name="Average kW",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=load_curve["local_hour"],
                y=load_curve["p95_kw"],
                mode="lines+markers",
                name="P95 kW",
            )
        )
        fig.update_layout(
            title="Peak Demand Curve",
            xaxis_title="Local Hour",
            yaxis_title="Estimated kW",
            height=430,
            margin=dict(l=20, r=20, t=60, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

bottom_left, bottom_right = st.columns(2)
with bottom_left:
    if not daily.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=daily["metric_date"],
                y=daily["utilization_rate"] * 100,
                name="Daily utilization",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=daily["metric_date"],
                y=daily["rolling_7d_utilization"] * 100,
                mode="lines",
                name="7-day average",
            )
        )
        fig.update_layout(
            title="Charger Utilization Trend",
            xaxis_title="Date",
            yaxis_title="Utilization (%)",
            height=390,
            margin=dict(l=20, r=20, t=60, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

with bottom_right:
    if not storage.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=storage["month_start"],
                y=storage["shiftable_kwh"],
                name="Shiftable kWh",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=storage["month_start"],
                y=storage["savings_usd"],
                mode="lines+markers",
                yaxis="y2",
                name="Savings",
            )
        )
        fig.update_layout(
            title="Smart Charging Opportunity",
            xaxis_title="Month",
            yaxis_title="Shiftable kWh",
            yaxis2=dict(title="Savings ($)", overlaying="y", side="right"),
            height=390,
            margin=dict(l=20, r=20, t=60, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

if not storage.empty:
    total_shiftable = storage["shiftable_kwh"].sum()
    total_savings = storage["savings_usd"].sum()
    flexible_sessions = storage["flexible_sessions"].sum()
    st.subheader("Tesla Energy Recommendations")
    st.write(
        f"Shift approximately **{total_shiftable:,.0f} kWh** away from peak windows "
        f"across **{int(flexible_sessions):,} flexible sessions**, producing an estimated "
        f"**${total_savings:,.0f}** in energy arbitrage before demand-charge reductions. "
        "The highest-value controls are workplace smart charging, Powerwall-scale buffering "
        "for small sites, Megapack dispatch for fleet or campus peaks, and VPP enrollment "
        "when aggregate load can respond predictably."
    )
