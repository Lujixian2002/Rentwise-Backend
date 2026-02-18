import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius * c


def bbox(center_lat: float, center_lng: float, radius_km: float) -> tuple[float, float, float, float]:
    lat_delta = radius_km / 111.0
    lng_delta = radius_km / (111.0 * max(0.1, math.cos(math.radians(center_lat))))
    return (
        center_lat - lat_delta,
        center_lng - lng_delta,
        center_lat + lat_delta,
        center_lng + lng_delta,
    )
