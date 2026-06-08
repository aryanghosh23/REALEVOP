from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, text

from ev_charging_analytics.sql_utils import run_sql_file


LOGGER = logging.getLogger(__name__)


def get_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def initialize_database(engine: Engine, schema_path: Path) -> None:
    LOGGER.info("Initializing database schema from %s", schema_path)
    run_sql_file(engine, schema_path)


def truncate_core_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                TRUNCATE TABLE
                    raw_acn_sessions,
                    fact_charging_session,
                    dim_station,
                    dim_site
                RESTART IDENTITY CASCADE
                """
            )
        )


def load_raw_records(
    engine: Engine,
    records: list[dict[str, Any]],
    source_site_id: str,
) -> None:
    LOGGER.info("Loading %s raw ACN session records", len(records))
    rows = [
        {
            "source_site_id": source_site_id,
            "session_id": record.get("sessionID"),
            "payload": json.dumps(record),
        }
        for record in records
    ]
    if not rows:
        return

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO raw_acn_sessions (source_site_id, session_id, payload)
                VALUES (:source_site_id, :session_id, CAST(:payload AS JSONB))
                """
            ),
            rows,
        )


def load_curated_tables(
    engine: Engine,
    fact_sessions: pd.DataFrame,
    dim_site: pd.DataFrame,
    dim_station: pd.DataFrame,
) -> None:
    LOGGER.info("Loading curated dimensions and fact table")
    dim_site = dim_site.where(pd.notnull(dim_site), None)
    dim_station = dim_station.where(pd.notnull(dim_station), None)
    fact_sessions = fact_sessions.where(pd.notnull(fact_sessions), None)

    dim_site.to_sql("dim_site", engine, if_exists="append", index=False, method="multi")
    dim_station.to_sql(
        "dim_station", engine, if_exists="append", index=False, method="multi"
    )
    fact_sessions.to_sql(
        "fact_charging_session",
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1_000,
    )


def refresh_analytics_views(engine: Engine, views_path: Path) -> None:
    LOGGER.info("Refreshing analytics materialized views from %s", views_path)
    run_sql_file(engine, views_path)


def export_dashboard_tables(engine: Engine, export_dir: Path) -> None:
    """Export curated dashboard tables for Tableau or review without database access."""
    export_dir.mkdir(parents=True, exist_ok=True)
    queries = {
        "sessions.csv": "SELECT * FROM fact_charging_session",
        "hourly_site_load.csv": "SELECT * FROM mv_hourly_site_load",
        "daily_site_metrics.csv": "SELECT * FROM mv_daily_site_metrics",
        "smart_charging_opportunities.csv": "SELECT * FROM mv_smart_charging_opportunities",
    }

    with engine.connect() as connection:
        for filename, query in queries.items():
            df = pd.read_sql_query(query, connection)
            df.to_csv(export_dir / filename, index=False)
            LOGGER.info("Exported %s rows to %s", len(df), export_dir / filename)
