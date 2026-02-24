from __future__ import annotations

import json
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

GOOGLE_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def fetch_commute_minutes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    mode: str = "driving",
) -> int | None:
    if origin == destination:
        return 0

    settings = get_settings()
    if not settings.google_maps_api_key:
        return None

    params = urllib.parse.urlencode(
        {
            "origins": f"{origin[0]},{origin[1]}",
            "destinations": f"{destination[0]},{destination[1]}",
            "mode": mode,
            "units": "metric",
            "key": settings.google_maps_api_key,
        }
    )
    url = f"{GOOGLE_DISTANCE_MATRIX_URL}?{params}"
    req = Request(url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    rows = payload.get("rows") or []
    if not rows:
        return None
    elements = rows[0].get("elements") or []
    if not elements:
        return None
    element = elements[0]
    if element.get("status") != "OK":
        return None

    duration = element.get("duration", {}) or {}
    seconds = duration.get("value")
    try:
        return int(round(float(seconds) / 60.0))
    except (TypeError, ValueError):
        return None
