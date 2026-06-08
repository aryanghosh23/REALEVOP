from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ev_charging_analytics.config import PROJECT_ROOT


def generate_demo_exports(export_dir: Path | None = None) -> dict[str, int]:
    """Generate deterministic dashboard CSVs for local demos without Postgres."""
    rng = np.random.default_rng(42)
    export_dir = export_dir or PROJECT_ROOT / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    site_id = "caltech"
    station_ids = [f"CA-{idx:02d}" for idx in range(1, 19)]
    start = datetime(2020, 1, 1, 7)
    sessions: list[dict] = []

    session_num = 1
    for day_offset in range(90):
        day = start + timedelta(days=day_offset)
        is_weekend = day.weekday() >= 5
        session_count = int(rng.integers(45, 75) if not is_weekend else rng.integers(10, 28))

        for _ in range(session_count):
            station_id = rng.choice(station_ids)
            arrival_hour = int(
                rng.choice([7, 8, 9, 10, 11, 12, 13, 16, 17], p=[0.10, 0.22, 0.24, 0.12, 0.08, 0.06, 0.04, 0.08, 0.06])
                if not is_weekend
                else rng.choice([9, 10, 11, 12, 13, 14, 15, 16])
            )
            connection_time = day.replace(hour=arrival_hour, minute=int(rng.integers(0, 60)))
            duration_hr = float(np.clip(rng.normal(5.3 if not is_weekend else 2.7, 1.6), 0.8, 9.5))
            idle_hr = float(np.clip(rng.normal(1.1 if not is_weekend else 0.3, 0.7), 0, duration_hr - 0.25))
            charging_hr = max(duration_hr - idle_hr, 0.25)
            avg_charging_kw = float(np.clip(rng.normal(5.8, 1.1), 2.4, 7.2))
            kwh = charging_hr * avg_charging_kw
            disconnect_time = connection_time + timedelta(hours=duration_hr)
            done_time = connection_time + timedelta(hours=charging_hr)

            sessions.append(
                {
                    "session_id": f"demo-{session_num:06d}",
                    "acn_id": f"demo-acn-{session_num:06d}",
                    "site_id": site_id,
                    "cluster_id": "demo-garage",
                    "station_id": station_id,
                    "space_id": station_id,
                    "connection_time": connection_time.isoformat(),
                    "disconnect_time": disconnect_time.isoformat(),
                    "done_charging_time": done_time.isoformat(),
                    "connection_time_local": connection_time.isoformat(),
                    "disconnect_time_local": disconnect_time.isoformat(),
                    "connection_date": connection_time.date().isoformat(),
                    "connection_hour": connection_time.hour,
                    "connection_dow": connection_time.weekday(),
                    "connection_month": connection_time.strftime("%Y-%m"),
                    "is_weekend": is_weekend,
                    "kwh_delivered": round(kwh, 3),
                    "session_duration_min": round(duration_hr * 60, 2),
                    "charging_duration_min": round(charging_hr * 60, 2),
                    "idle_duration_min": round(idle_hr * 60, 2),
                    "avg_power_kw": round(kwh / duration_hr, 3),
                    "avg_charging_power_kw": round(avg_charging_kw, 3),
                    "kwh_requested": round(kwh + max(rng.normal(1.2, 1.4), -1.0), 3),
                    "miles_requested": round(kwh / 0.28, 1),
                    "minutes_available": round(duration_hr * 60, 1),
                    "energy_request_gap_kwh": round(max(rng.normal(1.2, 1.4), -1.0), 3),
                    "user_id_hash": f"demo-user-{int(rng.integers(1, 550)):04d}",
                    "timezone": "America/Los_Angeles",
                    "quality_flag": "valid",
                }
            )
            session_num += 1

    sessions_df = pd.DataFrame(sessions)
    hourly_rows: list[dict] = []
    for row in sessions_df.itertuples(index=False):
        connection = pd.Timestamp(row.connection_time)
        disconnect = pd.Timestamp(row.disconnect_time)
        hour = connection.floor("h")
        while hour < disconnect:
            next_hour = hour + pd.Timedelta(hours=1)
            overlap_hr = (
                min(disconnect, next_hour) - max(connection, hour)
            ).total_seconds() / 3600
            if overlap_hr > 0:
                hourly_rows.append(
                    {
                        "site_id": row.site_id,
                        "hour_bucket": hour.isoformat(),
                        "hour_bucket_local": hour.isoformat(),
                        "local_isodow": int(hour.isoweekday()),
                        "local_dow": int(hour.dayofweek),
                        "local_hour": int(hour.hour),
                        "active_sessions": 1,
                        "active_stations": 1,
                        "estimated_kwh": round(overlap_hr * row.avg_power_kw, 4),
                        "estimated_avg_kw": round(overlap_hr * row.avg_power_kw, 4),
                    }
                )
            hour = next_hour

    hourly_df = (
        pd.DataFrame(hourly_rows)
        .groupby(["site_id", "hour_bucket", "hour_bucket_local", "local_isodow", "local_dow", "local_hour"], as_index=False)
        .agg(
            active_sessions=("active_sessions", "sum"),
            active_stations=("active_stations", "sum"),
            estimated_kwh=("estimated_kwh", "sum"),
            estimated_avg_kw=("estimated_avg_kw", "sum"),
        )
    )

    daily_df = (
        sessions_df.groupby(["site_id", "connection_date"], as_index=False)
        .agg(
            session_count=("session_id", "count"),
            stations_used=("station_id", "nunique"),
            known_users=("user_id_hash", "nunique"),
            total_kwh=("kwh_delivered", "sum"),
            avg_session_kwh=("kwh_delivered", "mean"),
            avg_duration_min=("session_duration_min", "mean"),
            occupied_hours=("session_duration_min", lambda s: s.sum() / 60),
            charging_hours=("charging_duration_min", lambda s: s.sum() / 60),
            idle_hours=("idle_duration_min", lambda s: s.sum() / 60),
        )
        .rename(columns={"connection_date": "metric_date"})
    )
    daily_df["daily_capacity_hours"] = len(station_ids) * 24
    daily_df["utilization_rate"] = daily_df["occupied_hours"] / daily_df["daily_capacity_hours"]
    daily_df["active_charging_share"] = daily_df["charging_hours"] / daily_df["occupied_hours"]
    daily_df["rolling_7d_kwh"] = daily_df["total_kwh"].rolling(7, min_periods=1).mean()
    daily_df["rolling_7d_utilization"] = daily_df["utilization_rate"].rolling(7, min_periods=1).mean()

    storage_df = sessions_df.copy()
    storage_df["peak_window_kwh"] = np.where(
        storage_df["connection_hour"].between(16, 20),
        storage_df["kwh_delivered"] * 0.65,
        storage_df["kwh_delivered"] * 0.15,
    )
    storage_df["shiftable_kwh"] = np.where(
        storage_df["idle_duration_min"] >= 60,
        np.minimum(storage_df["kwh_delivered"], storage_df["peak_window_kwh"]),
        0,
    )
    storage_df["estimated_energy_cost_savings_usd"] = storage_df["shiftable_kwh"] * (0.42 - 0.18) * 0.90
    storage_df["recommendation"] = np.where(
        storage_df["shiftable_kwh"] > 0,
        "Defer charging or cover peak with onsite storage",
        "Low flexibility session",
    )
    storage_cols = [
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

    sessions_df.to_csv(export_dir / "sessions.csv", index=False)
    hourly_df.to_csv(export_dir / "hourly_site_load.csv", index=False)
    daily_df.to_csv(export_dir / "daily_site_metrics.csv", index=False)
    storage_df[storage_cols].to_csv(export_dir / "smart_charging_opportunities.csv", index=False)

    return {
        "sessions": len(sessions_df),
        "hourly_site_load": len(hourly_df),
        "daily_site_metrics": len(daily_df),
        "smart_charging_opportunities": len(storage_df),
    }


def main() -> None:
    counts = generate_demo_exports()
    print("Demo dashboard exports created:")
    for name, count in counts.items():
        print(f"- {name}: {count:,} rows")


if __name__ == "__main__":
    main()

