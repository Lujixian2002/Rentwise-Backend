
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
