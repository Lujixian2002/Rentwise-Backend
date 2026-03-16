from __future__ import annotations

import json
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

GOOGLE_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
GOOGLE_PLACE_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
GOOGLE_PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


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


def fetch_google_reviews(keyword: str) -> list[dict]:
    """
    Searches Google Maps for a place matching the keyword and fetches its reviews.
    Returns a list of review dictionaries.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        return []

    # 1. Search for the place to get its Place ID
    search_params = urllib.parse.urlencode(
        {
            "query": keyword,
            "key": settings.google_maps_api_key,
        }
    )
    search_url = f"{GOOGLE_PLACE_SEARCH_URL}?{search_params}"
    search_req = Request(search_url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(search_req, timeout=8) as resp:
            search_payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    results = search_payload.get("results") or []
    if not results:
        return []

    place_id = results[0].get("place_id")
    if not place_id:
        return []

    # 2. Fetch details using the Place ID to get reviews
    details_params = urllib.parse.urlencode(
        {
            "place_id": place_id,
            "fields": "name,rating,reviews",
            "key": settings.google_maps_api_key,
        }
    )
    details_url = f"{GOOGLE_PLACE_DETAILS_URL}?{details_params}"
    details_req = Request(details_url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(details_req, timeout=8) as resp:
            details_payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    result = details_payload.get("result") or {}
    reviews = result.get("reviews") or []
    
    return reviews
