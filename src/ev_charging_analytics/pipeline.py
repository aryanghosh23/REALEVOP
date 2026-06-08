from __future__ import annotations

import argparse
import logging
from pathlib import Path

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the EV charging ELT pipeline.")
    parser.add_argument("--site", help="ACN site id: caltech, jpl, or office001")
    parser.add_argument("--start", help="Connection start filter, e.g. 2019-01-01")
    parser.add_argument("--end", help="Connection end filter, e.g. 2020-12-31")
    parser.add_argument("--min-energy-kwh", type=float, help="Minimum delivered energy")
    parser.add_argument("--raw-json", type=Path, help="Offline ACN JSON export path")
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Use --raw-json or ACN_RAW_JSON instead of calling the ACN API.",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Append to existing tables instead of replacing the curated dataset.",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Export dashboard CSVs from existing database tables and exit.",
    )
    return parser.parse_args()


def run_pipeline(args: argparse.Namespace | None = None) -> dict[str, int]:
    args = args or parse_args()
    config = get_config()
    site = args.site or config.acn_site
    start = args.start or config.acn_start
    end = args.end or config.acn_end
    min_energy = (
        args.min_energy_kwh
        if args.min_energy_kwh is not None
        else config.acn_min_energy_kwh
    )
    raw_json = args.raw_json or config.acn_raw_json

    engine = get_engine(config.database_url)
    schema_path = PROJECT_ROOT / "sql" / "01_schema.sql"
    views_path = PROJECT_ROOT / "sql" / "03_dashboard_views.sql"

    if args.export_only:
        export_dashboard_tables(engine, PROJECT_ROOT / "data" / "exports")
        return {"export_only": 1}

    if args.skip_extract:
        if not raw_json.exists():
            raise FileNotFoundError(
                f"Raw JSON file not found: {raw_json}. Download from ACN-Data or run without --skip-extract."
            )
        records = load_raw_sessions(raw_json)
    else:
        if not config.acn_api_token:
            raise ValueError(
                "ACN_API_TOKEN is required for live extraction. Register at https://ev.caltech.edu/register "
                "or run with --skip-extract --raw-json path/to/export.json."
            )
        records = fetch_acn_sessions(
            site=site,
            api_token=config.acn_api_token,
            start=start,
            end=end,
            min_energy_kwh=min_energy,
            output_path=raw_json,
            base_url=config.settings.get("acn", {}).get(
                "base_url", "https://ev.caltech.edu/api/v1/"
            ),
        )

    fact_sessions = normalize_sessions(records, fallback_site_id=site)
    quality_metrics = validate_sessions(fact_sessions)
    dim_site, dim_station = build_dimensions(fact_sessions)

    processed_dir = PROJECT_ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    fact_sessions.to_parquet(processed_dir / "fact_charging_session.parquet", index=False)
    dim_site.to_parquet(processed_dir / "dim_site.parquet", index=False)
    dim_station.to_parquet(processed_dir / "dim_station.parquet", index=False)

    initialize_database(engine, schema_path)
    if not args.no_truncate:
        truncate_core_tables(engine)
    load_raw_records(engine, records, source_site_id=site)
    load_curated_tables(engine, fact_sessions, dim_site, dim_station)
    refresh_analytics_views(engine, views_path)
    export_dashboard_tables(engine, PROJECT_ROOT / "data" / "exports")

    LOGGER.info("Pipeline completed with quality metrics: %s", quality_metrics)
    return quality_metrics


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    run_pipeline()


if __name__ == "__main__":
    main()

