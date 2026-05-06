from __future__ import annotations

import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
OVERPASS_TIMEOUT_SEC = 8
OVERPASS_RETRY_ROUNDS = 2
OVERPASS_BACKOFF_BASE_SEC = 0.8


def fetch_grocery_density(
    center_lat: float, center_lng: float, radius_km: float = 1.0
) -> float | None:
    """
    Returns a weighted grocery accessibility density.
    Weight combines distance decay and a store-size proxy from OSM tags.
    """
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:8];
    (
      node(around:{radius_m},{center_lat},{center_lng})["shop"~"supermarket|grocery|convenience"];
      way(around:{radius_m},{center_lat},{center_lng})["shop"~"supermarket|grocery|convenience"];
    );
    out body center;
    """
    data = _query_overpass(query)
    if data is None:
        return None

    weighted_sum = 0.0
    for element in data.get("elements", []):
        lat, lng = _element_lat_lng(element)
        if lat is None or lng is None:
            continue
        distance_km = _haversine_km(center_lat, center_lng, lat, lng)
        distance_weight = _distance_decay_weight(distance_km, radius_km)
        size_weight = _grocery_size_weight(element.get("tags", {}))
        weighted_sum += distance_weight * size_weight

    area_km2 = math.pi * radius_km * radius_km
    if area_km2 <= 0:
        return None
    return round(weighted_sum / area_km2, 3)


def fetch_parking_metrics(
    center_lat: float, center_lng: float, radius_km: float = 1.2
) -> tuple[float | None, float | None, float | None]:
    """
    Returns parking supply and demand-pressure proxies:
    - public/customer parking lots per km2
    - mapped parking capacity per km2 when OSM capacity tags exist
    - POI demand density per km2 for places that tend to compete for parking
    """
    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:8];
    (
      node(around:{radius_m},{center_lat},{center_lng})["amenity"="parking"];
      way(around:{radius_m},{center_lat},{center_lng})["amenity"="parking"];
      relation(around:{radius_m},{center_lat},{center_lng})["amenity"="parking"];
      node(around:{radius_m},{center_lat},{center_lng})["amenity"="parking_space"];
      way(around:{radius_m},{center_lat},{center_lng})["amenity"="parking_space"];
      node(around:{radius_m},{center_lat},{center_lng})["amenity"~"restaurant|cafe|bar|pub|fast_food|school|college|university|cinema|theatre|place_of_worship|clinic|doctors|dentist|hospital"];
      way(around:{radius_m},{center_lat},{center_lng})["amenity"~"restaurant|cafe|bar|pub|fast_food|school|college|university|cinema|theatre|place_of_worship|clinic|doctors|dentist|hospital"];
      node(around:{radius_m},{center_lat},{center_lng})["shop"];
      way(around:{radius_m},{center_lat},{center_lng})["shop"];
      node(around:{radius_m},{center_lat},{center_lng})["office"];
      way(around:{radius_m},{center_lat},{center_lng})["office"];
    );
    out body center;
    """
    data = _query_overpass(query)
    if data is None:
        return None, None, None

    parking_weight = 0.0
    capacity_sum = 0.0
    poi_demand_weight = 0.0
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        lat, lng = _element_lat_lng(element)
        distance_weight = 1.0
        if lat is not None and lng is not None:
            distance_km = _haversine_km(center_lat, center_lng, lat, lng)
            distance_weight = _distance_decay_weight(distance_km, radius_km)

        if tags.get("amenity") in {"parking", "parking_space"}:
            access = (tags.get("access") or "").lower()
            if access in {"private", "no"}:
                continue
            parking_weight += distance_weight * _parking_facility_weight(tags)
            capacity = _parse_positive_float(tags.get("capacity"))
            if capacity is not None:
                capacity_sum += capacity * distance_weight
            elif tags.get("amenity") == "parking_space":
                capacity_sum += distance_weight
            continue

        poi_demand_weight += distance_weight * _parking_demand_weight(tags)

    area_km2 = math.pi * radius_km * radius_km
    if area_km2 <= 0:
        return None, None, None
    return (
        round(parking_weight / area_km2, 3),
        round(capacity_sum / area_km2, 3),
        round(poi_demand_weight / area_km2, 3),
    )


# def fetch_night_activity_index(
#     center_lat: float, center_lng: float, radius_km: float = 1.5
# ) -> float | None:
#     radius_m = int(radius_km * 1000)
#     query = f"""
#     [out:json][timeout:8];
#     (
#       node(around:{radius_m},{center_lat},{center_lng})["amenity"~"bar|pub|nightclub"];
#       way(around:{radius_m},{center_lat},{center_lng})["amenity"~"bar|pub|nightclub"];
#       node(around:{radius_m},{center_lat},{center_lng})["leisure"="stadium"];
#       way(around:{radius_m},{center_lat},{center_lng})["leisure"="stadium"];
#     );
#     out center;
#     """
#     data = _query_overpass(query)
#     if data is None:
#         return None

#     count = len(data.get("elements", []))
#     # 0-100 proxy: >=30 nearby venues saturates to 100.
#     return round(min(100.0, (count / 30.0) * 100.0), 2)


def fetch_noise_proxy(
    center_lat: float, center_lng: float, radius_km: float = 5.0
) -> tuple[float | None, float | None]:
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
        # Query succeeded but no noise-related features were found in range.
        return 0.0, 0.0

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
    # Retry by rotating endpoints first, then use exponential backoff between rounds.
    for round_idx in range(OVERPASS_RETRY_ROUNDS):
        for endpoint in OVERPASS_ENDPOINTS:
            req = Request(
                endpoint,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "User-Agent": "rentwise/1.0 (https://github.com/rentwise)",
                },
                method="POST",
            )
            try:
                with urlopen(req, timeout=OVERPASS_TIMEOUT_SEC) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                continue

        if round_idx < OVERPASS_RETRY_ROUNDS - 1:
            sleep_sec = OVERPASS_BACKOFF_BASE_SEC * (2**round_idx)
            time.sleep(sleep_sec)

    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return r * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def _element_lat_lng(element: dict) -> tuple[float | None, float | None]:
    if element.get("type") == "node":
        return element.get("lat"), element.get("lon")
    center = element.get("center")
    if isinstance(center, dict):
        return center.get("lat"), center.get("lon")
    return None, None


def _distance_decay_weight(distance_km: float, radius_km: float) -> float:
    # Closer stores matter much more than stores near the edge of the radius.
    decay_scale = max(0.25, radius_km / 3.0)
    return math.exp(-distance_km / decay_scale)


def _grocery_size_weight(tags: dict) -> float:
    shop = (tags.get("shop") or "").lower()
    base = {
        "supermarket": 1.0,
        "grocery": 0.75,
        "convenience": 0.45,
    }.get(shop, 0.6)

    area_m2 = _parse_positive_float(tags.get("shop:area")) or _parse_positive_float(
        tags.get("area")
    )
    if area_m2 is not None:
        # Soft scale: 100m2 ~ small, 2000m2+ ~ large.
        area_factor = min(1.8, max(0.7, math.log10(area_m2 + 10)))
        base *= area_factor

    levels = _parse_positive_float(tags.get("building:levels"))
    if levels is not None:
        level_factor = min(1.3, 1.0 + 0.05 * max(0.0, levels - 1.0))
        base *= level_factor

    return min(2.5, max(0.2, base))


def _parking_facility_weight(tags: dict) -> float:
    amenity = (tags.get("amenity") or "").lower()
    parking = (tags.get("parking") or "").lower()
    if amenity == "parking_space":
        return 0.15
    if parking in {"multi-storey", "underground"}:
        return 1.8
    if parking in {"street_side", "lane", "on_kerb", "half_on_kerb", "shoulder"}:
        return 0.6
    if parking == "surface" or not parking:
        return 1.0
    return 0.8


def _parking_demand_weight(tags: dict) -> float:
    amenity = (tags.get("amenity") or "").lower()
    if tags.get("office"):
        return 1.0
    if tags.get("shop"):
        return 0.8
    if amenity in {"restaurant", "cafe", "bar", "pub", "fast_food"}:
        return 1.0
    if amenity in {"school", "college", "university"}:
        return 1.2
    if amenity in {"cinema", "theatre"}:
        return 1.4
    if amenity in {"clinic", "doctors", "dentist", "hospital"}:
        return 1.1
    if amenity == "place_of_worship":
        return 0.7
    return 0.4


def _parse_positive_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    return parsed if parsed > 0 else None
