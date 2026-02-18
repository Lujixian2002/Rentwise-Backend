from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOCRATA_DOMAIN = "data.cityofirvine.org"
SOCRATA_CATALOG = "https://api.us.socrata.com/api/catalog/v1"
IRVINE_POPULATION = 307670


def fetch_crime_rate_per_100k(city: str | None) -> float | None:
    if city is None or city.lower() != "irvine":
        return None

    dataset_id, date_col = _discover_crime_dataset()
    if dataset_id is None:
        return None

    incidents = _count_recent_incidents(dataset_id, date_col)
    if incidents is None:
        return None

    return round((incidents / IRVINE_POPULATION) * 100000.0, 2)


def _discover_crime_dataset() -> tuple[str | None, str | None]:
    params = urllib.parse.urlencode(
        {
            "domains": SOCRATA_DOMAIN,
            "search_context": SOCRATA_DOMAIN,
            "q": "crime",
            "limit": 20,
        }
    )
    url = f"{SOCRATA_CATALOG}?{params}"
    payload = _get_json(url)
    if payload is None:
        return None, None

    for result in payload.get("results", []):
        resource = result.get("resource", {})
        name = (resource.get("name") or "").lower()
        description = (resource.get("description") or "").lower()
        if "crime" not in name and "crime" not in description:
            continue
        dataset_id = resource.get("id")
        if not dataset_id:
            continue
        cols = resource.get("columns_field_name", []) or []
        date_col = _choose_date_col(cols)
        return dataset_id, date_col
    return None, None


def _count_recent_incidents(dataset_id: str, date_col: str | None) -> int | None:
    base = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.json"
    where = None
    if date_col:
        one_year_ago = (datetime.now(tz=timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")
        where = f"{date_col} >= '{one_year_ago}'"

    params = {"$select": "count(1) as incident_count", "$limit": "1"}
    if where:
        params["$where"] = where

    url = f"{base}?{urllib.parse.urlencode(params)}"
    payload = _get_json(url)
    if not payload:
        return None
    raw = payload[0].get("incident_count")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _choose_date_col(columns: list[str]) -> str | None:
    preferred = ["date", "reported_date", "report_date", "occurred_date", "incident_date"]
    lowered = {c.lower(): c for c in columns}
    for key in preferred:
        if key in lowered:
            return lowered[key]
    for col in columns:
        if "date" in col.lower():
            return col
    return None


def _get_json(url: str) -> dict | list | None:
    req = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
