from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

ORS_BASE_URL = "https://api.openrouteservice.org/v2/directions"


def fetch_commute_minutes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    profile: str = "driving-car",
) -> int | None:
    if origin == destination:
        return 0

    settings = get_settings()
    if not settings.openrouteservice_api_key:
        return None

    url = f"{ORS_BASE_URL}/{profile}"
    # ORS requires [lng, lat]
    body = {
        "coordinates": [
            [origin[1], origin[0]],
            [destination[1], destination[0]],
        ]
    }
    data = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Authorization": settings.openrouteservice_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    features = payload.get("features") or []
    if not features:
        return None
    summary = ((features[0] or {}).get("properties") or {}).get("summary") or {}
    seconds = summary.get("duration")
    try:
        return int(round(float(seconds) / 60.0))
    except (TypeError, ValueError):
        return None
