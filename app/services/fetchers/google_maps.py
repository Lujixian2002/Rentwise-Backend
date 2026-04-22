from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

GOOGLE_ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

_TRAVEL_MODE_MAP = {
    "driving": "DRIVE",
    "walking": "WALK",
    "bicycling": "BICYCLE",
    "transit": "TRANSIT",
}


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

    travel_mode = _TRAVEL_MODE_MAP.get(mode, "DRIVE")
    body = {
        "origin": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}},
        "destination": {
            "location": {"latLng": {"latitude": destination[0], "longitude": destination[1]}}
        },
        "travelMode": travel_mode,
    }
    if travel_mode == "DRIVE":
        body["routingPreference"] = "TRAFFIC_AWARE"

    req = Request(
        GOOGLE_ROUTES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": "routes.duration",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    routes = payload.get("routes") or []
    if not routes:
        return None
    duration = routes[0].get("duration")  # e.g. "1200s"
    if not isinstance(duration, str) or not duration.endswith("s"):
        return None
    try:
        return int(round(float(duration[:-1]) / 60.0))
    except ValueError:
        return None
