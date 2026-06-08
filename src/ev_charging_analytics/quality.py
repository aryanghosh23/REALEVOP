from __future__ import annotations

import pandas as pd


def validate_sessions(df: pd.DataFrame) -> dict[str, int]:
    """Return data-quality metrics and raise on hard failures."""
    metrics = {
        "row_count": int(len(df)),
        "duplicate_session_ids": int(df["session_id"].duplicated().sum()),
        "missing_connection_time": int(df["connection_time"].isna().sum()),
        "missing_disconnect_time": int(df["disconnect_time"].isna().sum()),
        "negative_duration_rows": int((df["session_duration_min"] < 0).sum()),
        "negative_energy_rows": int((df["kwh_delivered"] < 0).sum()),
    }

    hard_failures = {
        key: value
        for key, value in metrics.items()
        if key != "row_count" and value > 0
    }
    if metrics["row_count"] == 0:
        raise ValueError("No charging sessions were produced by the transform step.")
    if hard_failures:
        raise ValueError(f"Charging session quality checks failed: {hard_failures}")

    return metrics

