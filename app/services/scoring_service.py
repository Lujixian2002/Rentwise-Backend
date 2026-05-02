from collections.abc import Mapping


PREFERENCE_DIMENSIONS = (
    "safety",
    "transit",
    "convenience",
    "parking",
    "environment",
)

CONVENIENCE_BASE_SCORE = 40.0
CONVENIENCE_FULL_SCORE_DENSITY = 0.5
DEFAULT_GROCERY_DENSITY = 0.25
DEFAULT_PARKING_LOT_DENSITY = 0.0
DEFAULT_PARKING_CAPACITY_DENSITY = 0.0
DEFAULT_POI_DEMAND_DENSITY = 1.0
PARKING_LOT_DENSITY_FULL_SCORE = 1.5
PARKING_CAPACITY_DENSITY_FULL_SCORE = 250.0
POI_DEMAND_DENSITY_HIGH_PRESSURE = 6.0

_WEIGHT_ALIASES = {
    "safety": "safety",
    "transit": "transit",
    "convenience": "convenience",
    "parking": "parking",
    "environment": "environment",
}


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _coalesce(value: float | None, default: float) -> float:
    """Return the value if not None — preserves legitimate zero readings."""
    return default if value is None else value


def compute_convenience_score(grocery_density_per_km2: float | None) -> float:
    grocery_density = _coalesce(
        grocery_density_per_km2, DEFAULT_GROCERY_DENSITY
    )
    return clamp_score(
        CONVENIENCE_BASE_SCORE
        + (grocery_density / CONVENIENCE_FULL_SCORE_DENSITY)
        * (100.0 - CONVENIENCE_BASE_SCORE)
    )


def compute_parking_score(metrics: Mapping[str, float | None]) -> float:
    parking_lot_density = _coalesce(
        metrics.get("parking_lot_density_per_km2"), DEFAULT_PARKING_LOT_DENSITY
    )
    parking_capacity = _coalesce(
        metrics.get("parking_capacity_per_km2"), DEFAULT_PARKING_CAPACITY_DENSITY
    )
    poi_demand_density = _coalesce(
        metrics.get("poi_demand_density_per_km2"), DEFAULT_POI_DEMAND_DENSITY
    )
    noise = _coalesce(metrics.get("noise_avg_db"), 55)
    night = _coalesce(metrics.get("night_activity_index"), 50)

    lot_supply_score = clamp_score(
        parking_lot_density / PARKING_LOT_DENSITY_FULL_SCORE * 100.0
    )
    capacity_supply_score = clamp_score(
        parking_capacity / PARKING_CAPACITY_DENSITY_FULL_SCORE * 100.0
    )
    parking_supply_score = (lot_supply_score * 0.7) + (capacity_supply_score * 0.3)

    demand_pressure = clamp_score(
        poi_demand_density / POI_DEMAND_DENSITY_HIGH_PRESSURE * 100.0
    )
    night_pressure = clamp_score(night)
    noise_pressure = clamp_score(((noise - 55.0) / 20.0) * 100.0)

    return clamp_score(
        parking_supply_score * 0.5
        + (100.0 - demand_pressure) * 0.2
        + (100.0 - night_pressure) * 0.15
        + (100.0 - noise_pressure) * 0.15
    )


def compute_quiet_score(noise_avg_db: float | None) -> float:
    noise = _coalesce(noise_avg_db, 55)
    return clamp_score(100.0 - max(0.0, noise - 55.0) * 4.0)


def compute_environment_score(metrics: Mapping[str, float | None]) -> float:
    quiet_score = compute_quiet_score(metrics.get("noise_avg_db"))
    night = _coalesce(metrics.get("night_activity_index"), 50)
    calm_night_score = clamp_score(100.0 - night)
    return clamp_score((quiet_score * 0.7) + (calm_night_score * 0.3))


def compute_dimension_scores(metrics: dict[str, float | None]) -> dict[str, float]:
    median_rent = _coalesce(metrics.get("median_rent"), 2500)
    commute_minutes = _coalesce(metrics.get("commute_minutes"), 30)
    grocery_density = _coalesce(
        metrics.get("grocery_density_per_km2"), DEFAULT_GROCERY_DENSITY
    )
    crime = _coalesce(metrics.get("crime_rate_per_100k"), 300)
    rent_trend = _coalesce(metrics.get("rent_trend_12m_pct"), 3.0)
    night = _coalesce(metrics.get("night_activity_index"), 50)
    review_score = _coalesce(metrics.get("review_signal_score"), 60)

    cost_score = clamp_score(100 - (median_rent / 50))
    transit_score = clamp_score(100 - (commute_minutes * 2.0))
    convenience_score = compute_convenience_score(grocery_density)
    safety_score = clamp_score(100 - (crime / 5))
    trend_score = clamp_score(100 - abs(rent_trend * 8))
    noise_score = compute_quiet_score(metrics.get("noise_avg_db"))
    nightlife_score = clamp_score(night * 1.2)
    reviews_score = clamp_score(review_score)
    parking_score = compute_parking_score(metrics)
    environment_score = compute_environment_score(metrics)

    return {
        "Cost": round(cost_score, 2),
        "Transit": round(transit_score, 2),
        "Convenience": round(convenience_score, 2),
        "Safety": round(safety_score, 2),
        "Trend": round(trend_score, 2),
        "Noise": round(noise_score, 2),
        "Nightlife": round(nightlife_score, 2),
        "Reviews": round(reviews_score, 2),
        "Parking": round(parking_score, 2),
        "Environment": round(environment_score, 2),
    }


def normalize_preference_weights(
    weights: Mapping[str, float | None] | None,
) -> dict[str, float]:
    if not weights:
        return _default_preference_weights()

    normalized_input = {dimension: 0.0 for dimension in PREFERENCE_DIMENSIONS}
    for raw_key, raw_value in weights.items():
        if raw_value is None:
            continue
        try:
            numeric_value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if numeric_value < 0:
            continue

        dimension = _WEIGHT_ALIASES.get(str(raw_key).strip().lower())
        if dimension:
            normalized_input[dimension] += numeric_value

    total = sum(normalized_input.values())
    if total <= 0:
        return _default_preference_weights()

    scaled = {
        dimension: round((value / total) * 100.0, 2)
        for dimension, value in normalized_input.items()
    }

    rounding_delta = round(100.0 - sum(scaled.values()), 2)
    scaled[PREFERENCE_DIMENSIONS[-1]] = round(
        scaled[PREFERENCE_DIMENSIONS[-1]] + rounding_delta, 2
    )
    return scaled


def normalize_preference_weights_to_ints(
    weights: Mapping[str, float | None] | None,
) -> dict[str, int]:
    normalized = normalize_preference_weights(weights)
    integer_weights = {
        dimension: int(normalized[dimension]) for dimension in PREFERENCE_DIMENSIONS
    }

    remainder = 100 - sum(integer_weights.values())
    ranked_dimensions = sorted(
        PREFERENCE_DIMENSIONS,
        key=lambda dimension: (
            normalized[dimension] - integer_weights[dimension],
            normalized[dimension],
        ),
        reverse=True,
    )

    for index in range(remainder):
        dimension = ranked_dimensions[index % len(ranked_dimensions)]
        integer_weights[dimension] += 1

    return integer_weights


def compute_preference_scores(
    metrics: Mapping[str, float | None],
) -> dict[str, float]:
    crime = _coalesce(metrics.get("crime_rate_per_100k"), 300)
    commute_minutes = _coalesce(metrics.get("commute_minutes"), 30)
    grocery_density = _coalesce(
        metrics.get("grocery_density_per_km2"), DEFAULT_GROCERY_DENSITY
    )
    safety_score = clamp_score(100 - (crime / 5))
    transit_score = clamp_score(100 - (commute_minutes * 2.0))
    convenience_score = compute_convenience_score(grocery_density)

    parking_score = compute_parking_score(metrics)
    environment_score = compute_environment_score(metrics)

    return {
        "safety": round(safety_score, 2),
        "transit": round(transit_score, 2),
        "convenience": round(convenience_score, 2),
        "parking": round(parking_score, 2),
        "environment": round(environment_score, 2),
    }


def compute_weighted_preference_score(
    scores: Mapping[str, float],
    weights: Mapping[str, float | None] | None,
) -> tuple[dict[str, float], float]:
    normalized_weights = normalize_preference_weights(weights)
    contributions = {
        dimension: round(
            scores.get(dimension, 0.0) * normalized_weights[dimension] / 100.0, 2
        )
        for dimension in PREFERENCE_DIMENSIONS
    }
    total_score = round(sum(contributions.values()), 2)
    return contributions, total_score


def _default_preference_weights() -> dict[str, float]:
    equal_weight = round(100.0 / len(PREFERENCE_DIMENSIONS), 2)
    weights = {dimension: equal_weight for dimension in PREFERENCE_DIMENSIONS}
    weights[PREFERENCE_DIMENSIONS[-1]] = round(
        100.0 - sum(weights.values()) + weights[PREFERENCE_DIMENSIONS[-1]], 2
    )
    return weights
