from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from airflow.decorators import dag, task

from ev_charging_analytics.config import PROJECT_ROOT, get_config
from ev_charging_analytics.extract import fetch_acn_sessions, load_raw_sessions
from ev_charging_analytics.load import (
    export_dashboard_tables,
    get_engine,
    initialize_database,
    load_curated_tables,
    load_raw_records,
    refresh_analytics_views,
    truncate_core_tables,
)
from ev_charging_analytics.quality import validate_sessions
from ev_charging_analytics.transform import build_dimensions, normalize_sessions


LOGGER = logging.getLogger(__name__)


@dag(
    dag_id="ev_charging_acn_elt",
    description="ACN-Data EV charging ELT pipeline for energy analytics dashboard.",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["ev", "energy", "postgres", "portfolio"],
)
def ev_charging_acn_elt():
    @task
    def extract_sessions() -> str:
        config = get_config()
        raw_path = config.acn_raw_json

        if config.acn_api_token:
            records = fetch_acn_sessions(
                site=config.acn_site,
                api_token=config.acn_api_token,
                start=config.acn_start,
                end=config.acn_end,
                min_energy_kwh=config.acn_min_energy_kwh,
                output_path=raw_path,
                base_url=config.settings.get("acn", {}).get(
                    "base_url", "https://ev.caltech.edu/api/v1/"
                ),
            )
        else:
            records = load_raw_sessions(raw_path)

        LOGGER.info("Extracted %s sessions to %s", len(records), raw_path)
        return str(raw_path)

    @task
    def transform_sessions(raw_path: str) -> dict[str, str]:
        config = get_config()
        records = load_raw_sessions(Path(raw_path))
        fact = normalize_sessions(records, fallback_site_id=config.acn_site)
        metrics = validate_sessions(fact)
        dim_site, dim_station = build_dimensions(fact)

        processed_dir = PROJECT_ROOT / "data" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        fact_path = processed_dir / "fact_charging_session.parquet"
        site_path = processed_dir / "dim_site.parquet"
        station_path = processed_dir / "dim_station.parquet"
        metrics_path = processed_dir / "quality_metrics.json"

        fact.to_parquet(fact_path, index=False)
        dim_site.to_parquet(site_path, index=False)
        dim_station.to_parquet(station_path, index=False)
        metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

        return {
            "fact": str(fact_path),
            "dim_site": str(site_path),
            "dim_station": str(station_path),
            "metrics": str(metrics_path),
            "raw": raw_path,
        }

    @task
    def load_postgres(paths: dict[str, str]) -> None:
        config = get_config()
        engine = get_engine(config.database_url)
        records = load_raw_sessions(Path(paths["raw"]))
        fact = pd.read_parquet(paths["fact"])
        dim_site = pd.read_parquet(paths["dim_site"])
        dim_station = pd.read_parquet(paths["dim_station"])

        initialize_database(engine, PROJECT_ROOT / "sql" / "01_schema.sql")
        truncate_core_tables(engine)
        load_raw_records(engine, records, source_site_id=config.acn_site)
        load_curated_tables(engine, fact, dim_site, dim_station)

    @task
    def refresh_marts_and_exports() -> None:
        config = get_config()
        engine = get_engine(config.database_url)
        refresh_analytics_views(engine, PROJECT_ROOT / "sql" / "03_dashboard_views.sql")
        export_dashboard_tables(engine, PROJECT_ROOT / "data" / "exports")

    raw = extract_sessions()
    transformed = transform_sessions(raw)
    load_postgres(transformed) >> refresh_marts_and_exports()


ev_charging_acn_elt()

