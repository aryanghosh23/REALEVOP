from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PipelineConfig:
    database_url: str
    acn_api_token: str | None
    acn_site: str
    acn_start: str | None
    acn_end: str | None
    acn_min_energy_kwh: float | None
    acn_raw_json: Path
    settings: dict


def load_settings(path: Path | None = None) -> dict:
    """Load project YAML settings."""
    settings_path = path or PROJECT_ROOT / "config" / "pipeline.yaml"
    with settings_path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def get_config() -> PipelineConfig:
    """Load runtime configuration from .env/environment and YAML defaults."""
    load_dotenv(PROJECT_ROOT / ".env")
    settings = load_settings()
    acn_defaults = settings.get("acn", {})

    raw_json = Path(os.getenv("ACN_RAW_JSON", "data/raw/acn_sessions_caltech.json"))
    if not raw_json.is_absolute():
        raw_json = PROJECT_ROOT / raw_json

    min_energy = os.getenv("ACN_MIN_ENERGY_KWH")

    return PipelineConfig(
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://ev_user:ev_password@localhost:5432/ev_charging",
        ),
        acn_api_token=os.getenv("ACN_API_TOKEN") or None,
        acn_site=os.getenv("ACN_SITE", acn_defaults.get("default_site", "caltech")),
        acn_start=os.getenv("ACN_START") or None,
        acn_end=os.getenv("ACN_END") or None,
        acn_min_energy_kwh=float(min_energy) if min_energy not in (None, "") else None,
        acn_raw_json=raw_json,
        settings=settings,
    )

