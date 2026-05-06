from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.core.config import Settings
from app.services.fetchers.crimegrade import fetch_crimegrade_violent_rate_per_100k
from app.services.fetchers.google_maps import (
    fetch_commute_minutes as fetch_google_commute_minutes,
)
from app.services.fetchers.irvine_crime import fetch_crime_rate_per_100k_with_source
from app.services.fetchers.local_crime import fetch_crime_rate_per_100k as fetch_local_crime_rate
from app.services.fetchers.nasa_viirs import fetch_viirs_night_activity_index
from app.services.fetchers.openrouteservice import (
    fetch_commute_minutes as fetch_ors_commute_minutes,
)
from app.services.fetchers.overpass_osm import (
    fetch_grocery_density,
    fetch_noise_proxy,
    fetch_parking_metrics,
)


@dataclass
class DimensionToolResult:
    dimension: str
    status: str
    metrics: dict[str, float | None] = field(default_factory=dict)
    source: str = "none"
    confidence: str = "low"
    missing_fields: list[str] = field(default_factory=list)
    detail: str | None = None


def fetch_safety_dimension(
    name: str,
    city: str | None,
    state: str | None,
    center_lat: float | None,
    center_lng: float | None,
) -> DimensionToolResult:
    crime_rate, source = fetch_crimegrade_violent_rate_per_100k(name, city, state)
    if crime_rate is None:
        crime_rate, source = fetch_crime_rate_per_100k_with_source(
            city,
            center_lat=center_lat,
            center_lng=center_lng,
        )
    if crime_rate is None:
        crime_rate, source = fetch_local_crime_rate(
            city,
            state=state,
        )

    if crime_rate is None:
        return DimensionToolResult(
            dimension="safety",
            status="failed",
            source=source,
            missing_fields=["crime_rate_per_100k"],
            detail="Crime source tools did not return a rate.",
        )

    return DimensionToolResult(
        dimension="safety",
        status="success",
        metrics={"crime_rate_per_100k": crime_rate},
        source=source,
        confidence="medium" if source.startswith("fallback:") else "high",
    )


def fetch_transit_dimension(
    settings: Settings,
    center_lat: float | None,
    center_lng: float | None,
) -> DimensionToolResult:
    if center_lat is None or center_lng is None:
        return DimensionToolResult(
            dimension="transit",
            status="failed",
            missing_fields=["commute_minutes"],
            detail="Missing coordinates for commute calculation.",
        )

    origin = (center_lat, center_lng)
    destination = (settings.commute_destination_lat, settings.commute_destination_lng)
    first_source = "google_maps" if settings.prefer_google_commute else "openrouteservice"
    second_source = "openrouteservice" if settings.prefer_google_commute else "google_maps"

    minutes = _fetch_commute_by_source(first_source, origin, destination)
    source = first_source
    if minutes is None:
        minutes = _fetch_commute_by_source(second_source, origin, destination)
        source = second_source

    if minutes is None:
        return DimensionToolResult(
            dimension="transit",
            status="failed",
            source=f"{first_source}->{second_source}",
            missing_fields=["commute_minutes"],
            detail="Primary and fallback commute tools failed.",
        )

    return DimensionToolResult(
        dimension="transit",
        status="success",
        metrics={"commute_minutes": float(minutes)},
        source=source,
        confidence="high",
    )


def fetch_convenience_dimension(
    center_lat: float | None,
    center_lng: float | None,
) -> DimensionToolResult:
    if center_lat is None or center_lng is None:
        return DimensionToolResult(
            dimension="convenience",
            status="failed",
            missing_fields=["grocery_density_per_km2"],
            detail="Missing coordinates for amenity lookup.",
        )

    grocery_density = fetch_grocery_density(center_lat, center_lng, radius_km=1.2)
    if grocery_density is None:
        return DimensionToolResult(
            dimension="convenience",
            status="failed",
            source="overpass_grocery",
            missing_fields=["grocery_density_per_km2"],
            detail="Overpass grocery lookup did not return data.",
        )

    return DimensionToolResult(
        dimension="convenience",
        status="success",
        metrics={"grocery_density_per_km2": grocery_density},
        source="overpass_grocery",
        confidence="medium",
    )


def fetch_parking_dimension(
    center_lat: float | None,
    center_lng: float | None,
) -> DimensionToolResult:
    if center_lat is None or center_lng is None:
        return DimensionToolResult(
            dimension="parking",
            status="failed",
            missing_fields=[
                "parking_lot_density_per_km2",
                "parking_capacity_per_km2",
                "poi_demand_density_per_km2",
            ],
            detail="Missing coordinates for parking lookup.",
        )

    parking_lot_density, parking_capacity, poi_demand_density = fetch_parking_metrics(
        center_lat,
        center_lng,
    )
    metrics = {
        "parking_lot_density_per_km2": parking_lot_density,
        "parking_capacity_per_km2": parking_capacity,
        "poi_demand_density_per_km2": poi_demand_density,
    }
    missing = [key for key, value in metrics.items() if value is None]
    if len(missing) == len(metrics):
        return DimensionToolResult(
            dimension="parking",
            status="failed",
            source="overpass_parking",
            missing_fields=missing,
            detail="Overpass parking lookup did not return data.",
        )

    return DimensionToolResult(
        dimension="parking",
        status="success",
        metrics=metrics,
        source="overpass_parking",
        confidence="medium" if missing else "high",
        missing_fields=missing,
    )


def fetch_environment_dimension(
    center_lat: float | None,
    center_lng: float | None,
) -> DimensionToolResult:
    if center_lat is None or center_lng is None:
        return DimensionToolResult(
            dimension="environment",
            status="failed",
            missing_fields=["noise_avg_db", "night_activity_index"],
            detail="Missing coordinates for environment lookup.",
        )

    noise_avg_db, noise_p90_db = fetch_noise_proxy(center_lat, center_lng)
    night_activity_index = fetch_viirs_night_activity_index(center_lat, center_lng)
    metrics = {
        "noise_avg_db": noise_avg_db,
        "noise_p90_db": noise_p90_db,
        "night_activity_index": night_activity_index,
    }
    missing = [key for key, value in metrics.items() if value is None]
    if len(missing) == len(metrics):
        return DimensionToolResult(
            dimension="environment",
            status="failed",
            source="overpass_noise+viirs",
            missing_fields=missing,
            detail="Noise and night-activity tools did not return data.",
        )

    return DimensionToolResult(
        dimension="environment",
        status="success",
        metrics=metrics,
        source="overpass_noise+viirs",
        confidence="medium" if missing else "high",
        missing_fields=missing,
    )


def fetch_all_dimension_tools(
    settings: Settings,
    name: str,
    city: str | None,
    state: str | None,
    center_lat: float | None,
    center_lng: float | None,
) -> list[DimensionToolResult]:
    return fetch_selected_dimension_tools(
        settings=settings,
        dimensions=["safety", "transit", "convenience", "parking", "environment"],
        name=name,
        city=city,
        state=state,
        center_lat=center_lat,
        center_lng=center_lng,
    )


async def fetch_all_dimension_tools_async(
    settings: Settings,
    name: str,
    city: str | None,
    state: str | None,
    center_lat: float | None,
    center_lng: float | None,
) -> list[DimensionToolResult]:
    return await fetch_selected_dimension_tools_async(
        settings=settings,
        dimensions=["safety", "transit", "convenience", "parking", "environment"],
        name=name,
        city=city,
        state=state,
        center_lat=center_lat,
        center_lng=center_lng,
    )


def fetch_selected_dimension_tools(
    settings: Settings,
    dimensions: list[str],
    name: str,
    city: str | None,
    state: str | None,
    center_lat: float | None,
    center_lng: float | None,
) -> list[DimensionToolResult]:
    requested = set(dimensions)
    results: list[DimensionToolResult] = []

    if "safety" in requested:
        results.append(
            fetch_safety_dimension(
                name=name,
                city=city,
                state=state,
                center_lat=center_lat,
                center_lng=center_lng,
            )
        )
    if "transit" in requested:
        results.append(fetch_transit_dimension(settings, center_lat, center_lng))
    if "convenience" in requested:
        results.append(fetch_convenience_dimension(center_lat, center_lng))
    if "parking" in requested:
        results.append(fetch_parking_dimension(center_lat, center_lng))
    if "environment" in requested:
        results.append(fetch_environment_dimension(center_lat, center_lng))
    return results


async def fetch_selected_dimension_tools_async(
    settings: Settings,
    dimensions: list[str],
    name: str,
    city: str | None,
    state: str | None,
    center_lat: float | None,
    center_lng: float | None,
) -> list[DimensionToolResult]:
    requested = set(dimensions)
    tasks = []

    if "safety" in requested:
        tasks.append(
            asyncio.to_thread(
                fetch_safety_dimension,
                name,
                city,
                state,
                center_lat,
                center_lng,
            )
        )
    if "transit" in requested:
        tasks.append(
            asyncio.to_thread(
                fetch_transit_dimension,
                settings,
                center_lat,
                center_lng,
            )
        )
    if "convenience" in requested:
        tasks.append(
            asyncio.to_thread(fetch_convenience_dimension, center_lat, center_lng)
        )
    if "parking" in requested:
        tasks.append(asyncio.to_thread(fetch_parking_dimension, center_lat, center_lng))
    if "environment" in requested:
        tasks.append(
            asyncio.to_thread(fetch_environment_dimension, center_lat, center_lng)
        )

    if not tasks:
        return []
    return list(await asyncio.gather(*tasks))


def _fetch_commute_by_source(
    source: str,
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> int | None:
    if source == "google_maps":
        return fetch_google_commute_minutes(origin, destination)
    if source == "openrouteservice":
        return fetch_ors_commute_minutes(origin, destination)
    return None
