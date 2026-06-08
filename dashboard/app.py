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
ACCENT = "#39ff14"
ACCENT_BLUE = "#00a3ff"
ACCENT_AMBER = "#f6c85f"
TEXT = "#f5f7fa"
MUTED = "#8f9baa"
PANEL = "rgba(7, 11, 15, 0.78)"
GRID = "rgba(255, 255, 255, 0.10)"
COLORWAY = [ACCENT_BLUE, ACCENT, ACCENT_AMBER, "#ff3d71", "#ffffff", "#7c5cff"]


load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="EV Charging Energy Optimization",
    page_icon="EV",
    layout="wide",
)

st.markdown(
    f"""
    <style>
    :root {{
        --accent: {ACCENT};
        --accent-blue: {ACCENT_BLUE};
        --accent-amber: {ACCENT_AMBER};
        --text: {TEXT};
        --muted: {MUTED};
        --panel: {PANEL};
        --grid: {GRID};
        --line: rgba(57, 255, 20, 0.28);
        --glass: rgba(9, 14, 20, 0.72);
        --glass-strong: rgba(7, 10, 14, 0.88);
    }}

    .stApp {{
        color: var(--text);
        background:
            linear-gradient(145deg, #020305 0%, #05090e 42%, #070b10 100%),
            repeating-linear-gradient(90deg, rgba(0,163,255,0.055) 0 1px, transparent 1px 68px),
            repeating-linear-gradient(0deg, rgba(57,255,20,0.035) 0 1px, transparent 1px 68px);
    }}

    [data-testid="stHeader"] {{
        background: rgba(2, 3, 5, 0.82);
        backdrop-filter: blur(14px);
    }}

    [data-testid="stSidebar"] {{
        background: rgba(3, 5, 8, 0.97);
        border-right: 1px solid rgba(0, 163, 255, 0.28);
        box-shadow: 10px 0 35px rgba(0, 0, 0, 0.32);
    }}

    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3 {{
        color: var(--text);
    }}

    .block-container {{
        padding-top: 1.15rem;
        padding-bottom: 2.6rem;
        max-width: 1540px;
    }}

    h1, h2, h3, p, label, span {{
        letter-spacing: 0;
    }}

    .ev-header {{
        position: relative;
        padding: 20px 22px 18px 22px;
        border: 1px solid rgba(0, 163, 255, 0.34);
        border-radius: 8px;
        background:
            linear-gradient(110deg, rgba(3, 8, 13, 0.96), rgba(6, 10, 14, 0.86) 52%, rgba(2, 14, 10, 0.92));
        box-shadow:
            0 22px 55px rgba(0, 0, 0, 0.44),
            inset 0 1px 0 rgba(255, 255, 255, 0.10),
            inset 0 -1px 0 rgba(57, 255, 20, 0.22);
        overflow: hidden;
        margin-bottom: 10px;
    }}

    .ev-header::before {{
        content: "";
        position: absolute;
        inset: 0;
        background:
            repeating-linear-gradient(90deg, rgba(0, 163, 255, 0.12) 0 1px, transparent 1px 44px),
            repeating-linear-gradient(0deg, rgba(57, 255, 20, 0.07) 0 1px, transparent 1px 44px),
            linear-gradient(180deg, rgba(255, 255, 255, 0.09), transparent 46%);
        pointer-events: none;
    }}

    .ev-header-content {{
        position: relative;
        z-index: 1;
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 18px;
    }}

    .eyebrow {{
        margin: 0 0 5px 0;
        color: var(--accent);
        font-size: 0.72rem;
        font-weight: 780;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}

    .ev-title {{
        margin: 0;
        color: var(--text);
        font-size: clamp(1.7rem, 3.1vw, 3.0rem);
        font-weight: 820;
        line-height: 1.05;
        text-transform: uppercase;
    }}

    .ev-subtitle {{
        margin: 8px 0 0 0;
        color: var(--muted);
        max-width: 880px;
        font-size: 0.98rem;
        line-height: 1.45;
    }}

    .status-badge {{
        flex: 0 0 auto;
        min-width: 184px;
        padding: 12px 14px;
        border-radius: 8px;
        border: 1px solid rgba(57, 255, 20, 0.36);
        background: rgba(2, 7, 8, 0.76);
        text-align: right;
    }}

    .status-badge .label {{
        display: block;
        color: var(--muted);
        font-size: 0.74rem;
        text-transform: uppercase;
        font-weight: 700;
    }}

    .status-badge .value {{
        display: block;
        color: var(--accent);
        font-size: 1.05rem;
        font-weight: 760;
        margin-top: 2px;
    }}

    .ops-tape {{
        display: grid;
        grid-template-columns: repeat(6, minmax(0, 1fr));
        gap: 1px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 8px;
        overflow: hidden;
        margin: 0 0 16px 0;
        background: rgba(255, 255, 255, 0.10);
        box-shadow: 0 14px 35px rgba(0, 0, 0, 0.28);
    }}

    .tape-cell {{
        min-height: 58px;
        padding: 10px 12px;
        background: rgba(3, 7, 11, 0.84);
    }}

    .tape-label {{
        display: block;
        color: var(--muted);
        font-size: 0.64rem;
        font-weight: 780;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }}

    .tape-value {{
        display: block;
        margin-top: 4px;
        color: var(--text);
        font-size: 1.02rem;
        font-weight: 810;
    }}

    .tape-value.hot {{
        color: var(--accent);
    }}

    .tape-value.blue {{
        color: var(--accent-blue);
    }}

    .metric-tile {{
        min-height: 112px;
        padding: 15px 16px 14px 16px;
        border-radius: 8px;
        border: 1px solid rgba(0, 163, 255, 0.28);
        background: linear-gradient(145deg, rgba(6, 10, 14, 0.82), rgba(3, 7, 11, 0.72));
        backdrop-filter: blur(14px);
        box-shadow:
            0 16px 34px rgba(0,0,0,0.30),
            inset 0 1px 0 rgba(255,255,255,0.08);
    }}

    .metric-label {{
        color: var(--muted);
        font-size: 0.70rem;
        font-weight: 800;
        text-transform: uppercase;
        margin-bottom: 8px;
        letter-spacing: 0.06em;
    }}

    .metric-value {{
        color: var(--text);
        font-size: clamp(1.25rem, 2vw, 1.8rem);
        font-weight: 790;
        line-height: 1.05;
    }}

    .metric-accent {{
        width: 44px;
        height: 3px;
        margin-top: 14px;
        border-radius: 2px;
        background: linear-gradient(90deg, var(--accent-blue), var(--accent));
        box-shadow: 0 0 18px rgba(57, 255, 20, 0.42);
    }}

    .section-title {{
        color: var(--text);
        font-size: 1.02rem;
        font-weight: 760;
        margin: 20px 0 8px 0;
    }}

    .insight-panel {{
        padding: 18px 20px;
        border-radius: 8px;
        border: 1px solid rgba(57, 255, 20, 0.30);
        background: linear-gradient(135deg, rgba(3, 8, 13, 0.88), rgba(4, 17, 10, 0.78));
        box-shadow: 0 18px 38px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.08);
        margin-top: 12px;
    }}

    .insight-panel h3 {{
        margin: 0 0 8px 0;
        color: var(--accent);
        font-size: 1.1rem;
        text-transform: uppercase;
    }}

    .insight-panel p {{
        color: #d7dde3;
        line-height: 1.55;
        margin: 0;
    }}

    [data-testid="stSelectbox"] > div,
    [data-testid="stDateInput"] > div {{
        border-radius: 8px;
    }}

    div[data-testid="stPlotlyChart"] {{
        border: 1px solid rgba(0, 163, 255, 0.20);
        border-radius: 8px;
        background: rgba(3, 7, 11, 0.70);
        backdrop-filter: blur(12px);
        padding: 6px;
        box-shadow: 0 18px 38px rgba(0,0,0,0.30);
    }}

    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div {{
        background: rgba(3, 7, 11, 0.84);
        border-color: rgba(0, 163, 255, 0.32);
    }}

    [data-testid="stCaptionContainer"] {{
        color: var(--accent);
    }}

    @media (max-width: 760px) {{
        .ops-tape {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .ev-header-content {{
            align-items: flex-start;
            flex-direction: column;
        }}
        .status-badge {{
            width: 100%;
            text-align: left;
        }}
        .metric-tile {{
            min-height: 96px;
        }}
    }}
    </style>
    """,
    unsafe_allow_html=True,
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


def format_compact(value: float, suffix: str = "") -> str:
    if pd.isna(value):
        return "0"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{suffix}"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K{suffix}"
    return f"{value:,.0f}{suffix}"


def metric_tile(label: str, value: str) -> None:
    st.markdown(
        (
            '<div class="metric-tile">'
            f'<div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div>'
            '<div class="metric-accent"></div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def ops_tape(items: list[tuple[str, str, str]]) -> None:
    cells = "".join(
        (
            '<div class="tape-cell">'
            f'<span class="tape-label">{label}</span>'
            f'<span class="tape-value {tone}">{value}</span>'
            "</div>"
        )
        for label, value, tone in items
    )
    st.markdown(f'<div class="ops-tape">{cells}</div>', unsafe_allow_html=True)


def style_figure(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(2,5,8,0.62)",
        colorway=COLORWAY,
        font=dict(color=TEXT, family="Inter, Segoe UI, Arial, sans-serif"),
        title=dict(font=dict(size=18, color=TEXT), x=0.02, xanchor="left"),
        height=height,
        margin=dict(l=24, r=24, t=64, b=34),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, title_font=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, title_font=dict(color=MUTED))
    return fig


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
        storage["connection_time"] = pd.to_datetime(storage["connection_time"], utc=True)
        mask = (
            (storage["site_id"] == site_id)
            & (storage["connection_time"].dt.date >= start_date)
            & (storage["connection_time"].dt.date <= end_date)
        )
        storage = storage.loc[mask].copy()
        storage["month_start"] = (
            storage["connection_time"]
            .dt.tz_convert(None)
            .dt.to_period("M")
            .dt.to_timestamp()
        )
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
    storage["connection_time"] = pd.to_datetime(storage["connection_time"], utc=True)
    mask = (
        (storage["site_id"] == site_id)
        & (storage["connection_time"].dt.date >= start_date)
        & (storage["connection_time"].dt.date <= end_date)
    )
    storage = storage.loc[mask].copy()
    storage["month_start"] = (
        storage["connection_time"]
        .dt.tz_convert(None)
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    return (
        storage.groupby("month_start", as_index=False)
        .agg(
            shiftable_kwh=("shiftable_kwh", "sum"),
            savings_usd=("estimated_energy_cost_savings_usd", "sum"),
            flexible_sessions=("shiftable_kwh", lambda x: int((x > 0).sum())),
        )
        .sort_values("month_start")
    )


sites, min_date, max_date = load_filter_options()
source_label = "CSV exports" if _exports_ready() else ("PostgreSQL" if db_available() else "No data")

st.markdown(
    f"""
    <div class="ev-header">
        <div class="ev-header-content">
            <div>
                <p class="eyebrow">Tesla Energy Portfolio Analytics</p>
                <h1 class="ev-title">EV Energy Control Room</h1>
                <p class="ev-subtitle">
                    ACN load telemetry // charger utilization // peak demand // storage dispatch
                </p>
            </div>
            <div class="status-badge">
                <span class="label">Active Source</span>
                <span class="value">{source_label}</span>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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
    st.caption(f"Source: {source_label}")

kpis = query_kpis(selected_site, start_date, end_date)
if kpis.empty:
    st.warning("No sessions matched the selected filters.")
    st.stop()

kpi = kpis.iloc[0].fillna(0)
heatmap = query_heatmap(selected_site, start_date, end_date)
daily = query_daily(selected_site, start_date, end_date)
load_curve = query_load_curve(selected_site, start_date, end_date)
storage = query_storage(selected_site, start_date, end_date)

peak_kw = float(load_curve["p95_kw"].max()) if not load_curve.empty else 0.0
avg_utilization = float(daily["utilization_rate"].mean() * 100) if not daily.empty else 0.0
shiftable_kwh = float(storage["shiftable_kwh"].sum()) if not storage.empty else 0.0
savings_usd = float(storage["savings_usd"].sum()) if not storage.empty else 0.0

ops_tape(
    [
        ("Grid Load P95", f"{peak_kw:,.1f} kW", "blue"),
        ("Avg Utilization", f"{avg_utilization:,.1f}%", ""),
        ("Storage Flex", format_compact(shiftable_kwh, " kWh"), "hot"),
        ("Arbitrage", f"${savings_usd:,.0f}", "hot"),
        ("Data Window", f"{start_date:%b %Y} - {end_date:%b %Y}", ""),
        ("Control Mode", "CSV LIVE", "blue"),
    ]
)

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    metric_tile("Sessions", f"{int(kpi['sessions']):,}")
with col2:
    metric_tile("Stations", f"{int(kpi['stations']):,}")
with col3:
    metric_tile("Energy", format_compact(float(kpi["total_kwh"]), " kWh"))
with col4:
    metric_tile("Avg Session", f"{kpi['avg_duration_hr']:.1f} hr")
with col5:
    metric_tile("Avg Idle", f"{kpi['avg_idle_hr']:.1f} hr")

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
            color_continuous_scale=["#03070b", "#052338", ACCENT_BLUE, ACCENT, "#ffffff"],
            labels={"x": "Hour", "y": "Day", "color": "kWh"},
            title="Load Heatmap // kWh by Hour",
        )
        fig = style_figure(fig, 430)
        fig.update_coloraxes(colorbar=dict(title="kWh", tickfont=dict(color=MUTED)))
        st.plotly_chart(fig, width="stretch")

with right:
    if not load_curve.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=load_curve["local_hour"],
                y=load_curve["avg_kw"],
                mode="lines+markers",
                name="Average kW",
                line=dict(width=3, color=ACCENT),
                marker=dict(size=7, color=ACCENT),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=load_curve["local_hour"],
                y=load_curve["p95_kw"],
                mode="lines+markers",
                name="P95 kW",
                line=dict(width=3, color=ACCENT_AMBER),
                marker=dict(size=7, color=ACCENT_AMBER),
            )
        )
        fig = style_figure(fig, 430)
        fig.update_layout(title="Peak Curve // Average vs P95", xaxis_title="Local Hour", yaxis_title="Estimated kW")
        st.plotly_chart(fig, width="stretch")

bottom_left, bottom_right = st.columns(2)
with bottom_left:
    if not daily.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=daily["metric_date"],
                y=daily["utilization_rate"] * 100,
                name="Daily utilization",
                marker=dict(color="rgba(123, 183, 255, 0.78)", line=dict(color=ACCENT_BLUE, width=1)),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=daily["metric_date"],
                y=daily["rolling_7d_utilization"] * 100,
                mode="lines",
                name="7-day average",
                line=dict(width=3, color=ACCENT),
            )
        )
        fig = style_figure(fig, 390)
        fig.update_layout(title="Utilization Signal // Daily Occupancy", xaxis_title="Date", yaxis_title="Utilization (%)")
        st.plotly_chart(fig, width="stretch")

with bottom_right:
    if not storage.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=storage["month_start"],
                y=storage["shiftable_kwh"],
                name="Shiftable kWh",
                marker=dict(color="rgba(63, 247, 198, 0.76)", line=dict(color=ACCENT, width=1)),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=storage["month_start"],
                y=storage["savings_usd"],
                mode="lines+markers",
                yaxis="y2",
                name="Savings",
                line=dict(width=3, color=ACCENT_AMBER),
                marker=dict(size=7, color=ACCENT_AMBER),
            )
        )
        fig = style_figure(fig, 390)
        fig.update_layout(
            title="Storage Dispatch Window // Shiftable Load",
            xaxis_title="Month",
            yaxis_title="Shiftable kWh",
            yaxis2=dict(
                title="Savings ($)",
                overlaying="y",
                side="right",
                gridcolor="rgba(0,0,0,0)",
                title_font=dict(color=MUTED),
                tickfont=dict(color=MUTED),
            ),
        )
        st.plotly_chart(fig, width="stretch")

if not storage.empty:
    total_shiftable = storage["shiftable_kwh"].sum()
    total_savings = storage["savings_usd"].sum()
    flexible_sessions = storage["flexible_sessions"].sum()
    st.markdown(
        f"""
        <div class="insight-panel">
            <h3>Energy Control Dispatch</h3>
            <p>
                Shift approximately <strong>{total_shiftable:,.0f} kWh</strong> away from peak windows
                across <strong>{int(flexible_sessions):,} flexible sessions</strong>, producing an estimated
                <strong>${total_savings:,.0f}</strong> in energy arbitrage before demand-charge reductions.
                The highest-value controls are workplace smart charging, Powerwall-scale buffering for compact
                sites, Megapack dispatch for campus peaks, and VPP enrollment when aggregate load can respond
                predictably.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
