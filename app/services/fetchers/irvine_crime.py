from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from math import pi
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

# Used to convert incident counts to rate/100k for local radius area.
# If later you add census-based population by tract/zip, replace this estimate.
IRVINE_POPULATION = 307670
IRVINE_AREA_KM2 = 171.4


def fetch_crime_rate_per_100k(city: str | None) -> float | None:
    value, _ = fetch_crime_rate_per_100k_with_source(city)
    return value


def fetch_crime_rate_per_100k_with_source(
    city: str | None,
    center_lat: float | None = None,
    center_lng: float | None = None,
) -> tuple[float | None, str]:
    _ = city  # Kept for backward-compatible signature.
    settings = get_settings()

    if center_lat is None or center_lng is None:
        return _fallback_or_none(settings, "missing_coordinates")
    if not settings.crimeometer_api_key:
        return _fallback_or_none(settings, "missing_api_key")

    incident_count = _fetch_incident_count_from_crimeometer(
        lat=center_lat,
        lng=center_lng,
        radius_miles=settings.crimeometer_radius_miles,
        lookback_days=settings.crimeometer_lookback_days,
        api_key=settings.crimeometer_api_key,
        base_url=settings.crimeometer_base_url,
        timeout_sec=settings.crimeometer_timeout_sec,
    )
    if incident_count is None:
        return _fallback_or_none(settings, "request_failed")

    local_population = _estimate_population_for_radius_miles(settings.crimeometer_radius_miles)
    if local_population <= 0:
        return _fallback_or_none(settings, "invalid_population")

    rate = round((incident_count / local_population) * 100000.0, 2)
    return rate, "crimeometer"


def _fallback_or_none(settings, reason: str) -> tuple[float | None, str]:
    if settings.crime_enable_fallback:
        return settings.crime_fallback_per_100k, f"fallback:{reason}"
    return None, f"missing:{reason}"


def _fetch_incident_count_from_crimeometer(
    lat: float,
    lng: float,
    radius_miles: float,
    lookback_days: int,
    api_key: str,
    base_url: str,
    timeout_sec: int,
) -> int | None:
    now_utc = datetime.now(tz=timezone.utc)
    start_utc = now_utc - timedelta(days=max(1, lookback_days))

    params = {
        "lat": f"{lat:.7f}",
        "lon": f"{lng:.7f}",
        "distance": _format_distance_miles(radius_miles),
        "datetime_ini": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "datetime_end": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "x-api-key": api_key,
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=max(1, timeout_sec)) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    return _extract_incident_count(payload)


def _extract_incident_count(payload: dict | list) -> int | None:
    # Known/likely aggregate fields.
    if isinstance(payload, dict):
        for key in [
            "total_incidents",
            "incidents_total",
            "total",
            "count",
            "total_count",
            "records_total",
            "total_rows",
        ]:
            value = _to_int(payload.get(key))
            if value is not None:
                return value

        for key in ["incidents", "data", "results", "features"]:
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)

    if isinstance(payload, list):
        return len(payload)
    return None


def _to_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _estimate_population_for_radius_miles(radius_miles: float) -> float:
    radius_km = max(radius_miles, 0.1) * 1.60934
    area_km2 = pi * (radius_km**2)
    density = IRVINE_POPULATION / IRVINE_AREA_KM2
    return density * area_km2


def _format_distance_miles(radius_miles: float) -> str:
    rounded = round(max(radius_miles, 0.1), 2)
    if float(int(rounded)) == rounded:
        return f"{int(rounded)}mi"
    return f"{rounded}mi"
