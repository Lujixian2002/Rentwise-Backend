from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.db import crud
from app.schemas.chat import PreferenceWeights
from app.schemas.recommendation import (
    RecommendationItem,
    RecommendationMetricsPreview,
    RecommendationResponse,
)
from app.services.scoring_service import (
    compute_preference_scores,
    compute_weighted_preference_score,
    normalize_preference_weights,
)


def recommend_communities(
    db: Session,
    weights: dict[str, float] | None = None,
    top_k: int = 3,
) -> RecommendationResponse:
    normalized_weights = normalize_preference_weights(weights)

    rows = crud.list_communities_with_metrics(db)
    ranked: list[RecommendationItem] = []
    skipped_missing_metrics = 0

    for community, metrics in rows:
        if metrics is None:
            skipped_missing_metrics += 1
            continue

        commute_minutes = _extract_commute_minutes(metrics.details_json)
        score_input = {
            "crime_rate_per_100k": metrics.crime_rate_per_100k,
            "commute_minutes": commute_minutes,
            "grocery_density_per_km2": metrics.grocery_density_per_km2,
            "noise_avg_db": metrics.noise_avg_db,
            "night_activity_index": metrics.night_activity_index,
        }
        dimension_scores = compute_preference_scores(score_input)
        weighted_contributions, total_score = compute_weighted_preference_score(
            dimension_scores,
            normalized_weights,
        )

        ranked.append(
            RecommendationItem(
                rank=0,
                community_id=community.community_id,
                name=community.name,
                city=community.city,
                state=community.state,
                score=total_score,
                overall_confidence=metrics.overall_confidence,
                dimension_scores=PreferenceWeights(**dimension_scores),
                weighted_contributions=PreferenceWeights(**weighted_contributions),
                metrics=RecommendationMetricsPreview(
                    median_rent=metrics.median_rent,
                    grocery_density_per_km2=metrics.grocery_density_per_km2,
                    crime_rate_per_100k=metrics.crime_rate_per_100k,
                    noise_avg_db=metrics.noise_avg_db,
                    night_activity_index=metrics.night_activity_index,
                    commute_minutes=commute_minutes,
                ),
            )
        )

    ranked.sort(
        key=lambda item: (
            item.score,
            item.overall_confidence or 0.0,
            item.name.lower(),
        ),
        reverse=True,
    )

    top_ranked = ranked[:top_k]
    for index, item in enumerate(top_ranked, start=1):
        item.rank = index

    return RecommendationResponse(
        weights_used=PreferenceWeights(**normalized_weights),
        total_candidates=len(rows),
        scored_communities=len(ranked),
        skipped_missing_metrics=skipped_missing_metrics,
        ranked_communities=top_ranked,
    )


def _extract_commute_minutes(details_json: str | None) -> float | None:
    if not details_json:
        return None

    try:
        payload = json.loads(details_json)
    except json.JSONDecodeError:
        return None

    value = payload.get("sources", {}).get("commute_minutes")
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
