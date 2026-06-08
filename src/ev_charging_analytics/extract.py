from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


LOGGER = logging.getLogger(__name__)
DEFAULT_BASE_URL = "https://ev.caltech.edu/api/v1/"


def _format_acn_datetime(value: str | datetime) -> str:
    """Return ACN-compatible RFC 1123 UTC timestamp strings."""
    if isinstance(value, str):
        return value

    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt.astimezone(timezone.utc), usegmt=True)


def build_where_clause(
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    min_energy_kwh: float | None = None,
) -> str | None:
    conditions: list[str] = []
    if start is not None:
        conditions.append(f'connectionTime>="{_format_acn_datetime(start)}"')
    if end is not None:
        conditions.append(f'connectionTime<="{_format_acn_datetime(end)}"')
    if min_energy_kwh is not None:
        conditions.append(f"kWhDelivered>={min_energy_kwh}")
    return " and ".join(conditions) if conditions else None


def fetch_acn_sessions(
    *,
    site: str,
    api_token: str,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    min_energy_kwh: float | None = None,
    timeseries: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    output_path: Path | None = None,
    pause_seconds: float = 0.15,
) -> list[dict[str, Any]]:
    """Fetch ACN sessions by following the API's paginated HATEOAS links."""
    endpoint = f"sessions/{site}" + ("/ts" if timeseries else "")
    url = urljoin(base_url, endpoint)
    where = build_where_clause(start=start, end=end, min_energy_kwh=min_energy_kwh)
    params = {"sort": "-connectionTime"}
    if where:
        params["where"] = where

    client = requests.Session()
    records: list[dict[str, Any]] = []
    page = 1

    while url:
        LOGGER.info("Fetching ACN page %s from %s", page, url)
        response = client.get(
            url,
            params=params if page == 1 else None,
            auth=(api_token, ""),
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, list):
            items = payload
            next_href = None
        else:
            items = payload.get("_items") or payload.get("items") or payload.get("sessions") or []
            next_href = payload.get("_links", {}).get("next", {}).get("href")

        records.extend(items)
        LOGGER.info("Fetched %s cumulative sessions", len(records))

        url = urljoin(base_url, next_href) if next_href else None
        params = None
        page += 1
        if url:
            time.sleep(pause_seconds)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        LOGGER.info("Wrote raw ACN sessions to %s", output_path)

    return records


def load_raw_sessions(path: Path) -> list[dict[str, Any]]:
    """Load sessions from a JSON export or an ACN API response file."""
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("_items") or payload.get("items") or payload.get("sessions") or []

    raise ValueError(f"Unsupported raw ACN payload in {path}")

