from __future__ import annotations

import json
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import get_settings

PLACES_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def search_places(query: str, max_results: int = 5) -> list[str]:
    """
    Search Google Maps for places matching the query.
    Returns a list of place_ids.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        return []

    params = urllib.parse.urlencode(
        {
            "query": query,
            "key": settings.google_maps_api_key,
        }
    )
    url = f"{PLACES_TEXT_SEARCH_URL}?{params}"
    req = Request(url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return []

    results = data.get("results", [])
    place_ids = [r["place_id"] for r in results if "place_id" in r]
    return place_ids[:max_results]


def search_places_nearby(
    lat: float, lng: float, radius_m: int = 2000, place_type: str = "point_of_interest", max_results: int = 5
) -> list[str]:
    """
    Search for places near a coordinate using Nearby Search.
    Returns a list of place_ids.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        return []

    nearby_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = urllib.parse.urlencode(
        {
            "location": f"{lat},{lng}",
            "radius": radius_m,
            "type": place_type,
            "key": settings.google_maps_api_key,
        }
    )
    url = f"{nearby_url}?{params}"
    req = Request(url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        return []

    results = data.get("results", [])
    place_ids = [r["place_id"] for r in results if "place_id" in r]
    return place_ids[:max_results]


def fetch_place_reviews(place_id: str) -> list[dict]:
    """
    Fetch reviews for a given place_id using the Place Details API.
    Google returns up to 5 reviews per place.
    Returns a list of structured review dicts.
    """
    settings = get_settings()
    if not settings.google_maps_api_key:
        return []

    params = urllib.parse.urlencode(
        {
            "place_id": place_id,
            "fields": "name,reviews",
            "key": settings.google_maps_api_key,
        }
    )
    url = f"{PLACE_DETAILS_URL}?{params}"
    req = Request(url, headers={"Accept": "application/json"}, method="GET")

    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    if data.get("status") != "OK":
        return []

    result = data.get("result", {})
    place_name = result.get("name", "")
    raw_reviews = result.get("reviews", [])

    reviews = []
    for r in raw_reviews:
        # Google provides a unique combination of author + time as identifier
        author = r.get("author_name", "Unknown")
        time_val = r.get("time", 0)
        review_id = f"gmap-{place_id}-{time_val}"

        reviews.append(
            {
                "id": review_id,
                "text": r.get("text", ""),
                "author": author,
                "rating": r.get("rating"),
                "like_count": 0,
                "published_at": _unix_to_iso(time_val) if time_val else None,
                "parent_id": None,
                "place_id": place_id,
                "place_name": place_name,
            }
        )

    return reviews


def _unix_to_iso(ts: int) -> str:
    """Convert Unix timestamp to ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
