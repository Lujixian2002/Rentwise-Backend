from __future__ import annotations

import json
import urllib.parse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


def geocode_community(query: str) -> dict[str, str | float] | None:
    normalized = query.strip()
    if not normalized:
        return None

    # Bias ambiguous short names to Irvine area for this project.
    if "," not in normalized and "irvine" not in normalized.lower():
        normalized = f"{normalized}, Irvine, CA"

    params = urllib.parse.urlencode(
        {
            "q": normalized,
            "format": "jsonv2",
            "addressdetails": "1",
            "limit": "1",
        }
    )
    url = f"{NOMINATIM_SEARCH_URL}?{params}"
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "rentwise-backend/0.1 (community geocoding)",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    if not payload:
        return None

    top = payload[0]
    lat = _to_float(top.get("lat"))
    lng = _to_float(top.get("lon"))
    if lat is None or lng is None:
        return None

    address = top.get("address", {}) or {}
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
    )
    state = address.get("state_code") or address.get("state")
    if isinstance(state, str):
        state = state.upper()

    return {
        "name": top.get("name") or query.strip(),
        "display_name": top.get("display_name") or query.strip(),
        "lat": lat,
        "lng": lng,
        "city": city or None,
        "state": state or None,
    }


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None

