from collections.abc import Mapping


PREFERENCE_DIMENSIONS = (
    "safety",
    "transit",
    "convenience",
    "parking",
    "environment",
)

_WEIGHT_ALIASES = {
    "safety": "safety",
    "transit": "transit",
    "convenience": "convenience",
    "parking": "parking",
    "environment": "environment",
}


def clamp_score(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def compute_dimension_scores(metrics: dict[str, float | None]) -> dict[str, float]:
    median_rent = metrics.get("median_rent")
    commute_minutes = metrics.get("commute_minutes")
    grocery_density = metrics.get("grocery_density_per_km2")
    crime = metrics.get("crime_rate_per_100k")
    rent_trend = metrics.get("rent_trend_12m_pct")
    noise = metrics.get("noise_avg_db")
    night = metrics.get("night_activity_index")
    review_score = metrics.get("review_signal_score")

    cost_score = clamp_score(100 - ((median_rent or 2500) / 50))
    transit_score = clamp_score(100 - ((commute_minutes or 30) * 2.0))
    convenience_score = clamp_score((grocery_density or 8) * 6.5)
    safety_score = clamp_score(100 - ((crime or 300) / 5))
    trend_score = clamp_score(100 - abs((rent_trend or 3.0) * 8))
    noise_score = clamp_score(100 - ((noise or 55) * 1.5))
    nightlife_score = clamp_score((night or 50) * 1.2)
    reviews_score = clamp_score(review_score or 60)

    return {
        "Cost": round(cost_score, 2),
        "Transit": round(transit_score, 2),
        "Convenience": round(convenience_score, 2),
        "Safety": round(safety_score, 2),
        "Trend": round(trend_score, 2),
        "Noise": round(noise_score, 2),
        "Nightlife": round(nightlife_score, 2),
        "Reviews": round(reviews_score, 2),
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


def compute_preference_scores(
    metrics: Mapping[str, float | None],
) -> dict[str, float]:
    crime = metrics.get("crime_rate_per_100k")
    commute_minutes = metrics.get("commute_minutes")
    grocery_density = metrics.get("grocery_density_per_km2")
    noise = metrics.get("noise_avg_db")
    night = metrics.get("night_activity_index")

    safety_score = clamp_score(100 - ((crime or 300) / 5))
    transit_score = clamp_score(100 - ((commute_minutes or 30) * 2.0))
    convenience_score = clamp_score((grocery_density or 8) * 6.5)

    # Parking has no first-class data source yet, so we use a proxy:
    # lower density, lower night activity, and quieter streets tend to imply easier parking.
    parking_density_score = clamp_score(100 - ((grocery_density or 8) * 6.5))
    parking_noise_score = clamp_score(100 - ((noise or 55) * 1.0))
    parking_night_score = clamp_score(100 - ((night or 50) * 1.0))
    parking_score = (
        parking_density_score * 0.5
        + parking_noise_score * 0.25
        + parking_night_score * 0.25
    )

    quiet_score = clamp_score(100 - ((noise or 55) * 1.5))
    calm_night_score = clamp_score(100 - ((night or 50) * 1.2))
    environment_score = (quiet_score * 0.7) + (calm_night_score * 0.3)

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
