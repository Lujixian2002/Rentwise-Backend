import json

from sqlalchemy.orm import Session

from app.db import crud
from app.services.scoring_service import compute_dimension_scores


def compare_communities(
    db: Session,
    community_a_id: str,
    community_b_id: str,
    weights: dict[str, float] | None = None,
):
    weights = weights or {}

    metrics_a = crud.get_metrics(db, community_a_id)
    metrics_b = crud.get_metrics(db, community_b_id)

    if not metrics_a or not metrics_b:
        missing = []
        if not metrics_a:
            missing.append(f"missing metrics: {community_a_id}")
        if not metrics_b:
            missing.append(f"missing metrics: {community_b_id}")

        row = crud.create_comparison(
            db=db,
            community_a_id=community_a_id,
            community_b_id=community_b_id,
            request_params={"weights": weights},
            weights_used=weights,
            structured_diff={},
            short_summary="Comparison incomplete due to missing metrics",
            tradeoffs={},
            status="missing_data",
            missing_fields=missing,
        )
        return row, {}, {}

    dict_a = {
        "median_rent": metrics_a.median_rent,
        "commute_minutes": None,
        "grocery_density_per_km2": metrics_a.grocery_density_per_km2,
        "crime_rate_per_100k": metrics_a.crime_rate_per_100k,
        "rent_trend_12m_pct": metrics_a.rent_trend_12m_pct,
        "noise_avg_db": metrics_a.noise_avg_db,
        "night_activity_index": metrics_a.night_activity_index,
        "review_signal_score": None,
    }
    dict_b = {
        "median_rent": metrics_b.median_rent,
        "commute_minutes": None,
        "grocery_density_per_km2": metrics_b.grocery_density_per_km2,
        "crime_rate_per_100k": metrics_b.crime_rate_per_100k,
        "rent_trend_12m_pct": metrics_b.rent_trend_12m_pct,
        "noise_avg_db": metrics_b.noise_avg_db,
        "night_activity_index": metrics_b.night_activity_index,
        "review_signal_score": None,
    }

    score_a = compute_dimension_scores(dict_a)
    score_b = compute_dimension_scores(dict_b)

    structured_diff = {}
    for dim in sorted(score_a.keys()):
        structured_diff[dim] = {
            "a": score_a[dim],
            "b": score_b[dim],
            "winner": community_a_id if score_a[dim] >= score_b[dim] else community_b_id,
            "delta": round(score_a[dim] - score_b[dim], 2),
        }

    a_total = sum(score_a.values())
    b_total = sum(score_b.values())
    short_summary = (
        f"{community_a_id} leads overall" if a_total >= b_total else f"{community_b_id} leads overall"
    )

    tradeoffs = {
        "community_a_strengths": [k for k, v in structured_diff.items() if v["winner"] == community_a_id],
        "community_b_strengths": [k for k, v in structured_diff.items() if v["winner"] == community_b_id],
    }

    row = crud.create_comparison(
        db=db,
        community_a_id=community_a_id,
        community_b_id=community_b_id,
        request_params={"weights": weights},
        weights_used=weights,
        structured_diff=structured_diff,
        short_summary=short_summary,
        tradeoffs=tradeoffs,
        status="ready",
    )
    return row, structured_diff, tradeoffs


def parse_json(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default
