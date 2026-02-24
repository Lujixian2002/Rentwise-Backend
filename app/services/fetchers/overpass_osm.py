from __future__ import annotations

import json
import math
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SEC = 8


def fetch_grocery_density(center_lat: float, center_lng: float, radius_km: float = 1.0) -> float | None:
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:8];
    (
      node(around:{radius_m},{center_lat},{center_lng})["shop"~"supermarket|grocery|convenience"];
      way(around:{radius_m},{center_lat},{center_lng})["shop"~"supermarket|grocery|convenience"];
    );
    out center;
    """
    data = _query_overpass(query)
    if data is None:
        return None

    count = len(data.get("elements", []))
    area_km2 = math.pi * radius_km * radius_km
    if area_km2 <= 0:
        return None
    return round(count / area_km2, 3)


def fetch_night_activity_index(center_lat: float, center_lng: float, radius_km: float = 1.5) -> float | None:
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:8];
    (
      node(around:{radius_m},{center_lat},{center_lng})["amenity"~"bar|pub|nightclub"];
      way(around:{radius_m},{center_lat},{center_lng})["amenity"~"bar|pub|nightclub"];
      node(around:{radius_m},{center_lat},{center_lng})["leisure"="stadium"];
      way(around:{radius_m},{center_lat},{center_lng})["leisure"="stadium"];
    );
    out center;
    """
    data = _query_overpass(query)
    if data is None:
        return None

    count = len(data.get("elements", []))
    # 0-100 proxy: >=30 nearby venues saturates to 100.
    return round(min(100.0, (count / 30.0) * 100.0), 2)


def fetch_noise_proxy(center_lat: float, center_lng: float, radius_km: float = 5.0) -> tuple[float | None, float | None]:
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:8];
    (
      way(around:{radius_m},{center_lat},{center_lng})["highway"~"motorway|trunk|primary"];
      relation(around:{radius_m},{center_lat},{center_lng})["highway"~"motorway|trunk|primary"];
      way(around:{radius_m},{center_lat},{center_lng})["aeroway"="aerodrome"];
      relation(around:{radius_m},{center_lat},{center_lng})["aeroway"="aerodrome"];
    );
    out geom;
    """
    data = _query_overpass(query)
    if data is None:
        return None, None

    min_km: float | None = None
    for element in data.get("elements", []):
        geometry = element.get("geometry", [])
        for point in geometry:
            lat = point.get("lat")
            lng = point.get("lon")
            if lat is None or lng is None:
                continue
            dist = _haversine_km(center_lat, center_lng, lat, lng)
            if min_km is None or dist < min_km:
                min_km = dist

    if min_km is None:
        return None, None

    noise_avg = _distance_to_noise_db(min_km)
    noise_p90 = min(85.0, noise_avg + 7.0)
    return round(noise_avg, 2), round(noise_p90, 2)


def _distance_to_noise_db(distance_km: float) -> float:
    if distance_km <= 0.3:
        return 75.0
    if distance_km <= 1.0:
        return 68.0
    if distance_km <= 2.0:
        return 62.0
    return 55.0


def _query_overpass(query: str) -> dict | None:
    data = query.encode("utf-8")
    req = Request(
        OVERPASS_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=OVERPASS_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))
