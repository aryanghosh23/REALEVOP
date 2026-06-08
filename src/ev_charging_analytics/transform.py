from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import pandas as pd


SITE_NAMES = {
    "caltech": "Caltech campus garage",
    "jpl": "NASA Jet Propulsion Laboratory",
    "office001": "Silicon Valley office site",
}

SESSION_RENAME = {
    "_id": "acn_id",
    "clusterID": "cluster_id",
    "connectionTime": "connection_time",
    "disconnectTime": "disconnect_time",
    "doneChargingTime": "done_charging_time",
    "kWhDelivered": "kwh_delivered",
    "sessionID": "session_id",
    "siteID": "site_id",
    "spaceID": "space_id",
    "stationID": "station_id",
    "timezone": "timezone",
    "userID": "user_id",
}

USER_INPUT_RENAME = {
    "WhPerMile": "wh_per_mile",
    "kWhRequested": "kwh_requested",
    "milesRequested": "miles_requested",
    "minutesAvailable": "minutes_available",
    "modifiedAt": "user_input_modified_at",
    "paymentRequired": "payment_required",
    "requestedDeparture": "requested_departure",
}


def _parse_utc_datetime(df: pd.DataFrame, column: str) -> pd.Series:
    if column in df.columns:
        return pd.to_datetime(df[column], errors="coerce", utc=True)
    return pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns, UTC]")


def _hash_user_id(user_id: Any) -> str | None:
    if pd.isna(user_id) or user_id in ("", None):
        return None
    return hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()


def _latest_user_input(record: dict[str, Any]) -> dict[str, Any]:
    inputs = record.get("userInputs") or []
    if not inputs:
        return {"session_id": record.get("sessionID")}

    normalized = pd.DataFrame(inputs)
    if "modifiedAt" in normalized.columns:
        normalized["_modified_at"] = pd.to_datetime(
            normalized["modifiedAt"], errors="coerce", utc=True
        )
        latest = normalized.sort_values("_modified_at").iloc[-1].to_dict()
    else:
        latest = normalized.iloc[-1].to_dict()

    latest["session_id"] = record.get("sessionID")
    return {USER_INPUT_RENAME.get(key, key): value for key, value in latest.items()}


def _localize_timestamp(ts: pd.Timestamp, tz_name: str | None) -> pd.Timestamp | pd.NaT:
    if pd.isna(ts):
        return pd.NaT
    timezone = tz_name or "America/Los_Angeles"
    return ts.tz_convert(timezone).tz_localize(None)


def normalize_sessions(
    records: list[dict[str, Any]],
    fallback_site_id: str = "caltech",
) -> pd.DataFrame:
    """Normalize raw ACN session JSON into an analytics-ready fact table."""
    if not records:
        return pd.DataFrame()

    base = pd.json_normalize(records, max_level=1).rename(columns=SESSION_RENAME)
    user_inputs = pd.DataFrame([_latest_user_input(record) for record in records])

    if "session_id" not in base.columns:
        raise ValueError("Raw ACN data must include sessionID.")

    df = base.merge(user_inputs, on="session_id", how="left", suffixes=("", "_input"))

    for column in ["connection_time", "disconnect_time", "done_charging_time"]:
        df[column] = _parse_utc_datetime(df, column)
    for column in ["requested_departure", "user_input_modified_at"]:
        df[column] = _parse_utc_datetime(df, column)

    defaults = {
        "site_id": fallback_site_id,
        "timezone": "America/Los_Angeles",
        "station_id": "unknown_station",
        "space_id": "unknown_space",
        "cluster_id": "unknown_cluster",
        "user_id": pd.NA,
    }
    for column, default in defaults.items():
        if column not in df.columns:
            df[column] = default
        df[column] = df[column].fillna(default)

    numeric_columns = [
        "kwh_delivered",
        "wh_per_mile",
        "kwh_requested",
        "miles_requested",
        "minutes_available",
    ]
    for column in numeric_columns:
        if column not in df.columns:
            df[column] = np.nan
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df["connection_time_local"] = df.apply(
        lambda row: _localize_timestamp(row["connection_time"], row["timezone"]),
        axis=1,
    )
    df["disconnect_time_local"] = df.apply(
        lambda row: _localize_timestamp(row["disconnect_time"], row["timezone"]),
        axis=1,
    )

    charging_end = df["done_charging_time"].fillna(df["disconnect_time"])
    df["session_duration_min"] = (
        df["disconnect_time"] - df["connection_time"]
    ).dt.total_seconds() / 60.0
    df["charging_duration_min"] = (
        charging_end - df["connection_time"]
    ).dt.total_seconds() / 60.0
    df["charging_duration_min"] = df["charging_duration_min"].clip(lower=0)
    df["idle_duration_min"] = (
        df["session_duration_min"] - df["charging_duration_min"]
    ).clip(lower=0)

    session_hours = df["session_duration_min"] / 60.0
    charging_hours = df["charging_duration_min"].replace(0, np.nan) / 60.0
    df["avg_power_kw"] = (df["kwh_delivered"] / session_hours.replace(0, np.nan)).replace(
        [np.inf, -np.inf], np.nan
    )
    df["avg_charging_power_kw"] = (
        df["kwh_delivered"] / charging_hours
    ).replace([np.inf, -np.inf], np.nan)

    df["connection_date"] = df["connection_time_local"].dt.date
    df["connection_hour"] = df["connection_time_local"].dt.hour
    df["connection_dow"] = df["connection_time_local"].dt.dayofweek
    df["connection_month"] = df["connection_time_local"].dt.to_period("M").astype(str)
    df["is_weekend"] = df["connection_dow"].isin([5, 6])
    df["user_id_hash"] = df["user_id"].apply(_hash_user_id)
    df["energy_request_gap_kwh"] = df["kwh_requested"] - df["kwh_delivered"]

    valid = (
        df["session_id"].notna()
        & df["connection_time"].notna()
        & df["disconnect_time"].notna()
        & (df["session_duration_min"] > 0)
        & (df["kwh_delivered"].fillna(0) >= 0)
    )
    df["quality_flag"] = np.where(valid, "valid", "invalid_session")
    df = df.loc[valid].drop_duplicates(subset=["session_id"], keep="last").copy()

    keep_columns = [
        "session_id",
        "acn_id",
        "site_id",
        "cluster_id",
        "station_id",
        "space_id",
        "connection_time",
        "disconnect_time",
        "done_charging_time",
        "connection_time_local",
        "disconnect_time_local",
        "connection_date",
        "connection_hour",
        "connection_dow",
        "connection_month",
        "is_weekend",
        "kwh_delivered",
        "session_duration_min",
        "charging_duration_min",
        "idle_duration_min",
        "avg_power_kw",
        "avg_charging_power_kw",
        "wh_per_mile",
        "kwh_requested",
        "miles_requested",
        "minutes_available",
        "requested_departure",
        "payment_required",
        "user_input_modified_at",
        "energy_request_gap_kwh",
        "user_id_hash",
        "timezone",
        "quality_flag",
    ]
    for column in keep_columns:
        if column not in df.columns:
            df[column] = pd.NA

    return df[keep_columns].sort_values("connection_time").reset_index(drop=True)


def build_dimensions(fact_sessions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create site and station dimensions from transformed charging sessions."""
    site = (
        fact_sessions.groupby("site_id", dropna=False)
        .agg(
            timezone=("timezone", "first"),
            evse_count=("station_id", "nunique"),
            first_session_at=("connection_time", "min"),
            last_session_at=("connection_time", "max"),
        )
        .reset_index()
    )
    site["site_name"] = site["site_id"].map(SITE_NAMES).fillna(site["site_id"])
    site = site[
        [
            "site_id",
            "site_name",
            "timezone",
            "evse_count",
            "first_session_at",
            "last_session_at",
        ]
    ]

    station = (
        fact_sessions.groupby(["station_id", "site_id"], dropna=False)
        .agg(
            space_id=("space_id", "first"),
            first_seen_at=("connection_time", "min"),
            last_seen_at=("connection_time", "max"),
            session_count=("session_id", "count"),
            total_kwh_delivered=("kwh_delivered", "sum"),
        )
        .reset_index()
    )

    return site, station
