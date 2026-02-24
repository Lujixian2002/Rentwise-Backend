from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from math import cos, radians
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

SOCRATA_DOMAIN = "data.cityofirvine.org"
SOCRATA_CATALOG = "https://api.us.socrata.com/api/catalog/v1"
IRVINE_POPULATION = 307670
IRVINE_AREA_KM2 = 171.4
SOCRATA_TIMEOUT_SEC = 8
MAX_DATASET_CANDIDATES = 10
DEFAULT_RADIUS_KM = 2.0
MIN_AREA_KM2 = 0.05


def fetch_crime_rate_per_100k(city: str | None) -> float | None:
    value, _ = fetch_crime_rate_per_100k_with_source(city)
    return value


def fetch_crime_rate_per_100k_with_source(
    city: str | None,
    center_lat: float | None = None,
    center_lng: float | None = None,
) -> tuple[float | None, str]:
    if city is None or city.strip().lower() != "irvine":
        return None, "not_applicable"

    settings = get_settings()
    candidates = _discover_crime_datasets()
    if not candidates:
        return _fallback_or_none(settings)

    radius_km = DEFAULT_RADIUS_KM
    for dataset_id, columns in candidates:
        date_col = _choose_date_col(columns)
        geo_col = _choose_geo_col(columns)
        lat_col, lng_col = _choose_lat_lng_cols(columns)

        for where_clause in _build_where_clauses(columns, date_col):
            # Prefer geo-based local rate so nearby communities can differ.
            if center_lat is not None and center_lng is not None:
                incidents_local = _count_local_incidents(
                    dataset_id=dataset_id,
                    where_clause=where_clause,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    radius_km=radius_km,
                    geo_col=geo_col,
                    lat_col=lat_col,
                    lng_col=lng_col,
                )
                if incidents_local is not None:
                    pop_local = _estimate_population_for_radius(radius_km)
                    if pop_local > 0:
                        rate = round((incidents_local / pop_local) * 100000.0, 2)
                        return rate, f"socrata_local:{dataset_id}"

            incidents = _count_recent_incidents(dataset_id, where_clause)
            if incidents is not None and incidents > 0:
                return round((incidents / IRVINE_POPULATION) * 100000.0, 2), "socrata"

    return _fallback_or_none(settings)


def _fallback_or_none(settings) -> tuple[float | None, str]:
    if settings.crime_enable_fallback:
        return settings.crime_fallback_per_100k, "fallback"
    return None, "missing"


def _discover_crime_datasets() -> list[tuple[str, list[str]]]:
    params = urllib.parse.urlencode(
        {
            "domains": SOCRATA_DOMAIN,
            "search_context": SOCRATA_DOMAIN,
            "q": "crime incident police",
            "limit": 50,
        }
    )
    url = f"{SOCRATA_CATALOG}?{params}"
    payload = _get_json(url)
    if payload is None:
        return []

    ranked: list[tuple[int, str, list[str]]] = []
    for result in payload.get("results", []):
        resource = result.get("resource", {})
        dataset_id = resource.get("id")
        if not dataset_id:
            continue
        name = (resource.get("name") or "")
        description = (resource.get("description") or "")
        text = f"{name} {description}".lower()
        if "crime" not in text and "incident" not in text and "police" not in text:
            continue
        cols = resource.get("columns_field_name", []) or []
        score = _score_dataset(text, cols)
        ranked.append((score, dataset_id, cols))

    ranked.sort(key=lambda item: item[0], reverse=True)
    return [(dataset_id, cols) for _, dataset_id, cols in ranked[:MAX_DATASET_CANDIDATES]]


def _score_dataset(text: str, columns: list[str]) -> int:
    score = 0
    if "irvine" in text:
        score += 8
    if "crime" in text:
        score += 5
    if "incident" in text:
        score += 4
    if "police" in text:
        score += 2
    lower_cols = [c.lower() for c in columns]
    if any("date" in c for c in lower_cols):
        score += 2
    if any(c in lower_cols for c in ["city", "city_name", "jurisdiction", "agency"]):
        score += 1
    return score


def _count_recent_incidents(dataset_id: str, where_clause: str | None) -> int | None:
    base = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.json"
    params = {"$select": "count(1) as incident_count", "$limit": "1"}
    if where_clause:
        params["$where"] = where_clause

    url = f"{base}?{urllib.parse.urlencode(params)}"
    payload = _get_json(url)
    if not payload:
        return None
    raw = payload[0].get("incident_count")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _count_local_incidents(
    dataset_id: str,
    where_clause: str | None,
    center_lat: float,
    center_lng: float,
    radius_km: float,
    geo_col: str | None,
    lat_col: str | None,
    lng_col: str | None,
) -> int | None:
    if geo_col:
        return _count_with_geo_col(dataset_id, where_clause, center_lat, center_lng, radius_km, geo_col)
    if lat_col and lng_col:
        return _count_with_lat_lng_cols(
            dataset_id, where_clause, center_lat, center_lng, radius_km, lat_col, lng_col
        )
    return None


def _count_with_geo_col(
    dataset_id: str,
    where_clause: str | None,
    center_lat: float,
    center_lng: float,
    radius_km: float,
    geo_col: str,
) -> int | None:
    base = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.json"
    local_clause = (
        f"within_circle({geo_col}, {center_lat:.7f}, {center_lng:.7f}, {int(radius_km * 1000)})"
    )
    merged_where = _merge_where(where_clause, local_clause)
    params = {"$select": "count(1) as incident_count", "$limit": "1"}
    if merged_where:
        params["$where"] = merged_where
    url = f"{base}?{urllib.parse.urlencode(params)}"
    payload = _get_json(url)
    if not payload:
        return None
    raw = payload[0].get("incident_count")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _count_with_lat_lng_cols(
    dataset_id: str,
    where_clause: str | None,
    center_lat: float,
    center_lng: float,
    radius_km: float,
    lat_col: str,
    lng_col: str,
) -> int | None:
    base = f"https://{SOCRATA_DOMAIN}/resource/{dataset_id}.json"
    lat_delta, lng_delta = _lat_lng_deltas(center_lat, radius_km)
    bounds_clause = (
        f"{lat_col} >= {center_lat - lat_delta:.7f} AND {lat_col} <= {center_lat + lat_delta:.7f} "
        f"AND {lng_col} >= {center_lng - lng_delta:.7f} AND {lng_col} <= {center_lng + lng_delta:.7f}"
    )
    merged_where = _merge_where(where_clause, bounds_clause)
    params = {"$select": "count(1) as incident_count", "$limit": "1"}
    if merged_where:
        params["$where"] = merged_where
    url = f"{base}?{urllib.parse.urlencode(params)}"
    payload = _get_json(url)
    if not payload:
        return None
    raw = payload[0].get("incident_count")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _build_where_clauses(columns: list[str], date_col: str | None) -> list[str | None]:
    date_filter = None
    if date_col:
        one_year_ago = (datetime.now(tz=timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")
        date_filter = f"{date_col} >= '{one_year_ago}'"

    city_cols = [
        col
        for col in columns
        if col.lower() in {"city", "city_name", "jurisdiction", "agency", "reporting_district"}
    ]

    clauses: list[str | None] = []
    if city_cols:
        for city_col in city_cols:
            city_filter = f"lower({city_col}) like '%irvine%'"
            if date_filter:
                clauses.append(f"{date_filter} AND {city_filter}")
            clauses.append(city_filter)
    if date_filter:
        clauses.append(date_filter)
    clauses.append(None)

    # Keep order and uniqueness
    deduped: list[str | None] = []
    seen: set[str] = set()
    for clause in clauses:
        key = clause or "__none__"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(clause)
    return deduped


def _choose_date_col(columns: list[str]) -> str | None:
    preferred = [
        "date",
        "reported_date",
        "report_date",
        "occurred_date",
        "incident_date",
    ]
    lowered = {c.lower(): c for c in columns}
    for key in preferred:
        if key in lowered:
            return lowered[key]
    for col in columns:
        if "date" in col.lower():
            return col
    return None


def _choose_geo_col(columns: list[str]) -> str | None:
    preferred = [
        "location",
        "incident_location",
        "block_address",
        "geocoded_column",
        "geolocation",
    ]
    lowered = {c.lower(): c for c in columns}
    for key in preferred:
        if key in lowered:
            return lowered[key]
    for col in columns:
        text = col.lower()
        if "location" in text or "geocode" in text:
            return col
    return None


def _choose_lat_lng_cols(columns: list[str]) -> tuple[str | None, str | None]:
    lowered = {c.lower(): c for c in columns}
    lat_candidates = ["latitude", "lat", "y", "y_coord"]
    lng_candidates = ["longitude", "lon", "lng", "x", "x_coord"]
    lat_col = next((lowered[name] for name in lat_candidates if name in lowered), None)
    lng_col = next((lowered[name] for name in lng_candidates if name in lowered), None)
    return lat_col, lng_col


def _estimate_population_for_radius(radius_km: float) -> float:
    area_km2 = max(3.141592653589793 * (radius_km**2), MIN_AREA_KM2)
    density = IRVINE_POPULATION / IRVINE_AREA_KM2
    return density * area_km2


def _lat_lng_deltas(center_lat: float, radius_km: float) -> tuple[float, float]:
    lat_delta = radius_km / 111.0
    cos_lat = max(0.1, abs(cos(radians(center_lat))))
    lng_delta = radius_km / (111.0 * cos_lat)
    return lat_delta, lng_delta


def _merge_where(base_clause: str | None, extra_clause: str) -> str:
    if base_clause:
        return f"({base_clause}) AND ({extra_clause})"
    return extra_clause


def _get_json(url: str) -> dict | list | None:
    settings = get_settings()
    headers = {"Accept": "application/json"}
    if settings.socrata_app_token:
        headers["X-App-Token"] = settings.socrata_app_token
    req = Request(url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=SOCRATA_TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None
