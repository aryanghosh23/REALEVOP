from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ev_charging_analytics.config import PROJECT_ROOT
from ev_charging_analytics.extract import load_raw_sessions
from ev_charging_analytics.quality import validate_sessions
from ev_charging_analytics.transform import normalize_sessions


SITE_ID_ALIASES = {
    "0002": "caltech",
}


def _canonical_site_id(site_id: object) -> object:
    return SITE_ID_ALIASES.get(str(site_id), site_id)


def build_hourly_site_load(fact: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []

    for row in fact.itertuples(index=False):
        connection = pd.Timestamp(row.connection_time_local)
        disconnect = pd.Timestamp(row.disconnect_time_local)
        if pd.isna(connection) or pd.isna(disconnect) or disconnect <= connection:
            continue

        hour = connection.floor("h")
        while hour < disconnect:
            next_hour = hour + pd.Timedelta(hours=1)
            overlap_hr = (
                min(disconnect, next_hour) - max(connection, hour)
            ).total_seconds() / 3600.0
            if overlap_hr > 0:
                estimated_kw = row.avg_power_kw
                if pd.isna(estimated_kw) or estimated_kw <= 0:
                    estimated_kw = row.kwh_delivered / max(row.session_duration_min / 60.0, 0.01)

                rows.append(
                    {
                        "session_id": row.session_id,
                        "site_id": row.site_id,
                        "station_id": row.station_id,
                        "hour_bucket": hour.isoformat(),
                        "hour_bucket_local": hour.isoformat(),
                        "local_isodow": int(hour.isoweekday()),
                        "local_dow": int(hour.dayofweek),
                        "local_hour": int(hour.hour),
                        "estimated_kwh": overlap_hr * estimated_kw,
                    }
                )
            hour = next_hour

    if not rows:
        return pd.DataFrame(
            columns=[
                "site_id",
                "hour_bucket",
                "hour_bucket_local",
                "local_isodow",
                "local_dow",
                "local_hour",
                "active_sessions",
                "active_stations",
                "estimated_kwh",
                "estimated_avg_kw",
            ]
        )

    expanded = pd.DataFrame(rows)
    hourly = (
        expanded.groupby(
            [
                "site_id",
                "hour_bucket",
                "hour_bucket_local",
                "local_isodow",
                "local_dow",
                "local_hour",
            ],
            as_index=False,
        )
        .agg(
            active_sessions=("session_id", "nunique"),
            active_stations=("station_id", "nunique"),
            estimated_kwh=("estimated_kwh", "sum"),
        )
        .sort_values(["site_id", "hour_bucket"])
    )
    hourly["estimated_avg_kw"] = hourly["estimated_kwh"]
    return hourly


def build_daily_metrics(fact: pd.DataFrame) -> pd.DataFrame:
    station_counts = fact.groupby("site_id")["station_id"].nunique().to_dict()
    daily = (
        fact.groupby(["site_id", "connection_date"], as_index=False)
        .agg(
            session_count=("session_id", "count"),
            stations_used=("station_id", "nunique"),
            known_users=("user_id_hash", lambda s: s.dropna().nunique()),
            total_kwh=("kwh_delivered", "sum"),
            avg_session_kwh=("kwh_delivered", "mean"),
            avg_duration_min=("session_duration_min", "mean"),
            occupied_hours=("session_duration_min", lambda s: s.sum() / 60.0),
            charging_hours=("charging_duration_min", lambda s: s.sum() / 60.0),
            idle_hours=("idle_duration_min", lambda s: s.sum() / 60.0),
        )
        .rename(columns={"connection_date": "metric_date"})
        .sort_values(["site_id", "metric_date"])
    )
    daily["daily_capacity_hours"] = daily["site_id"].map(station_counts).clip(lower=1) * 24.0
    daily["utilization_rate"] = daily["occupied_hours"] / daily["daily_capacity_hours"]
    daily["active_charging_share"] = daily["charging_hours"] / daily["occupied_hours"].replace(0, np.nan)
    daily["rolling_7d_kwh"] = daily.groupby("site_id")["total_kwh"].transform(
        lambda s: s.rolling(7, min_periods=1).mean()
    )
    daily["rolling_7d_utilization"] = daily.groupby("site_id")["utilization_rate"].transform(
        lambda s: s.rolling(7, min_periods=1).mean()
    )
    return daily


def build_smart_charging_opportunities(fact: pd.DataFrame, hourly: pd.DataFrame) -> pd.DataFrame:
    session_hourly = []
    for row in fact.itertuples(index=False):
        connection = pd.Timestamp(row.connection_time_local)
        disconnect = pd.Timestamp(row.disconnect_time_local)
        hour = connection.floor("h")
        while hour < disconnect:
            next_hour = hour + pd.Timedelta(hours=1)
            overlap_hr = (
                min(disconnect, next_hour) - max(connection, hour)
            ).total_seconds() / 3600.0
            if overlap_hr > 0:
                estimated_kw = row.avg_power_kw
                if pd.isna(estimated_kw) or estimated_kw <= 0:
                    estimated_kw = row.kwh_delivered / max(row.session_duration_min / 60.0, 0.01)
                session_hourly.append(
                    {
                        "session_id": row.session_id,
                        "local_hour": int(hour.hour),
                        "estimated_kwh": overlap_hr * estimated_kw,
                    }
                )
            hour = next_hour

    if session_hourly:
        session_peak = (
            pd.DataFrame(session_hourly)
            .assign(
                peak_kwh=lambda df: np.where(
                    df["local_hour"].between(16, 20), df["estimated_kwh"], 0
                )
            )
            .groupby("session_id", as_index=False)["peak_kwh"]
            .sum()
            .rename(columns={"peak_kwh": "peak_window_kwh"})
        )
    else:
        session_peak = pd.DataFrame(columns=["session_id", "peak_window_kwh"])

    storage = fact.merge(session_peak, on="session_id", how="left")
    storage["peak_window_kwh"] = storage["peak_window_kwh"].fillna(0)
    storage["shiftable_kwh"] = np.where(
        storage["idle_duration_min"] >= 60,
        np.minimum(storage["kwh_delivered"], storage["peak_window_kwh"]),
        0,
    )
    storage["estimated_energy_cost_savings_usd"] = storage["shiftable_kwh"] * (0.42 - 0.18) * 0.90
    storage["recommendation"] = np.select(
        [
            storage["shiftable_kwh"] > 0,
            storage["idle_duration_min"] < 60,
        ],
        [
            "Defer charging or cover peak with onsite storage",
            "Low flexibility session",
        ],
        default="No peak-window charging detected",
    )
    return storage[
        [
            "session_id",
            "site_id",
            "station_id",
            "connection_time",
            "disconnect_time",
            "kwh_delivered",
            "session_duration_min",
            "charging_duration_min",
            "idle_duration_min",
            "peak_window_kwh",
            "shiftable_kwh",
            "estimated_energy_cost_savings_usd",
            "recommendation",
        ]
    ]


def export_from_raw_json(raw_json: Path, export_dir: Path | None = None) -> dict[str, int | str]:
    export_dir = export_dir or PROJECT_ROOT / "data" / "exports"
    processed_dir = PROJECT_ROOT / "data" / "processed"
    export_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    records = load_raw_sessions(raw_json)
    fact = normalize_sessions(records, fallback_site_id="caltech")
    fact["site_id"] = fact["site_id"].map(_canonical_site_id)
    validate_sessions(fact)

    hourly = build_hourly_site_load(fact)
    daily = build_daily_metrics(fact)
    storage = build_smart_charging_opportunities(fact, hourly)

    fact.to_parquet(processed_dir / "fact_charging_session.parquet", index=False)
    hourly.to_parquet(processed_dir / "hourly_site_load.parquet", index=False)
    daily.to_parquet(processed_dir / "daily_site_metrics.parquet", index=False)
    storage.to_parquet(processed_dir / "smart_charging_opportunities.parquet", index=False)

    fact.to_csv(export_dir / "sessions.csv", index=False)
    hourly.to_csv(export_dir / "hourly_site_load.csv", index=False)
    daily.to_csv(export_dir / "daily_site_metrics.csv", index=False)
    storage.to_csv(export_dir / "smart_charging_opportunities.csv", index=False)

    return {
        "source": str(raw_json),
        "sessions": len(fact),
        "hourly_site_load": len(hourly),
        "daily_site_metrics": len(daily),
        "smart_charging_opportunities": len(storage),
        "min_date": str(fact["connection_date"].min()),
        "max_date": str(fact["connection_date"].max()),
        "total_kwh": round(float(fact["kwh_delivered"].sum()), 2),
    }


def main() -> None:
    raw_json = PROJECT_ROOT / "data" / "raw" / "acn_sessions_caltech.json"
    counts = export_from_raw_json(raw_json)
    print("Real ACN dashboard exports created:")
    for key, value in counts.items():
        print(f"- {key}: {value}")


if __name__ == "__main__":
    main()

