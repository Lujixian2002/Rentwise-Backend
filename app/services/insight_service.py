from __future__ import annotations

import json

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import crud
from app.schemas.insight import CommunityInsightResponse, DimensionCommentary
from app.services.ingest_service import ensure_metrics_fresh, ensure_reviews_fresh
from app.services.scoring_service import (
    PREFERENCE_DIMENSIONS,
    compute_preference_scores,
)

_INSIGHT_SYSTEM_PROMPT = """You generate structured neighborhood insight cards for one community.
Ground every statement in the provided metrics and review excerpts only. Do not invent facts.

Return a valid JSON object with exactly this shape:
{
  "overall_commentary": "...",
  "dimensions": {
    "safety": "...",
    "transit": "...",
    "convenience": "...",
    "parking": "...",
    "environment": "..."
  }
}

Rules:
1. Each dimension commentary must be one short sentence.
2. Keep the tone helpful, concrete, and UI-friendly.
3. If evidence is thin, say that briefly instead of overstating.
4. "overall_commentary" should summarize the neighborhood's overall character in 1-2 short sentences.
5. For parking, use review evidence and proxy signals only; if evidence is limited, mention that."""


async def generate_community_insight(
    db: Session,
    community_id: str,
    settings: Settings,
    max_reviews: int = 20,
) -> CommunityInsightResponse | None:
    community = crud.get_community(db, community_id)
    if community is None:
        return None

    ensure_metrics_fresh(db, community_id)
    ensure_reviews_fresh(db, community_id)

    metrics = crud.get_metrics(db, community_id)
    reviews = crud.get_reviews_by_community(db, community_id, limit=max_reviews)

    score_input = {
        "crime_rate_per_100k": metrics.crime_rate_per_100k if metrics else None,
        "commute_minutes": _extract_commute_minutes(
            metrics.details_json if metrics else None
        ),
        "grocery_density_per_km2": (
            metrics.grocery_density_per_km2 if metrics else None
        ),
        "noise_avg_db": metrics.noise_avg_db if metrics else None,
        "night_activity_index": metrics.night_activity_index if metrics else None,
    }
    dimension_scores = compute_preference_scores(score_input)

    review_snippets = [
        _trim_review_text(review.body_text)
        for review in reviews
        if review.body_text and review.body_text.strip()
    ]
    review_snippets = [snippet for snippet in review_snippets if snippet]
    if not review_snippets:
        review_snippets = _extract_metric_review_snippets(metrics, limit=max_reviews)

    generated_copy = await _generate_insight_copy(
        settings=settings,
        community_name=community.name,
        city=community.city,
        state=community.state,
        dimension_scores=dimension_scores,
        metrics=metrics,
        review_snippets=review_snippets,
    )

    dimensions = [
        DimensionCommentary(
            dimension=dimension,
            commentary=generated_copy["dimensions"].get(
                dimension,
                _fallback_dimension_comment(dimension, dimension_scores[dimension]),
            ),
        )
        for dimension in PREFERENCE_DIMENSIONS
    ]

    return CommunityInsightResponse(
        community_id=community.community_id,
        name=community.name,
        city=community.city,
        state=community.state,
        posts_analyzed=len(review_snippets),
        dimensions=dimensions,
        overall_commentary=generated_copy.get("overall_commentary")
        or _fallback_overall_commentary(dimension_scores),
    )


async def _generate_insight_copy(
    settings: Settings,
    community_name: str,
    city: str | None,
    state: str | None,
    dimension_scores: dict[str, float],
    metrics,
    review_snippets: list[str],
) -> dict:
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0)
    metrics_context = {
        "median_rent": getattr(metrics, "median_rent", None),
        "crime_rate_per_100k": getattr(metrics, "crime_rate_per_100k", None),
        "grocery_density_per_km2": getattr(metrics, "grocery_density_per_km2", None),
        "noise_avg_db": getattr(metrics, "noise_avg_db", None),
        "night_activity_index": getattr(metrics, "night_activity_index", None),
        "overall_confidence": getattr(metrics, "overall_confidence", None),
        "commute_minutes": _extract_commute_minutes(
            getattr(metrics, "details_json", None)
        ),
    }
    user_prompt = json.dumps(
        {
            "community": {
                "name": community_name,
                "city": city,
                "state": state,
            },
            "dimension_scores": dimension_scores,
            "metrics": metrics_context,
            "review_excerpt_count": len(review_snippets),
            "review_excerpts": review_snippets[:20],
        },
        ensure_ascii=True,
    )

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _INSIGHT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=500,
        )
        raw = completion.choices[0].message.content or ""
        data = json.loads(raw)
        dimensions = data.get("dimensions", {})
        return {
            "overall_commentary": _clean_sentence(data.get("overall_commentary")),
            "dimensions": {
                dimension: _clean_sentence(dimensions.get(dimension))
                for dimension in PREFERENCE_DIMENSIONS
                if dimensions.get(dimension)
            },
        }
    except Exception:
        return {
            "overall_commentary": _fallback_overall_commentary(dimension_scores),
            "dimensions": {
                dimension: _fallback_dimension_comment(dimension, score)
                for dimension, score in dimension_scores.items()
            },
        }


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


def _trim_review_text(text: str, limit: int = 220) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _extract_metric_review_snippets(metrics, limit: int) -> list[str]:
    if metrics is None or limit <= 0:
        return []

    snippets: list[str] = []
    for item in _extract_texts(metrics.youtube_comments):
        snippet = _trim_review_text(item)
        if snippet:
            snippets.append(snippet)
        if len(snippets) >= limit:
            return snippets
    return snippets


def _extract_texts(raw_json: str | None) -> list[str]:
    if not raw_json:
        return []

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError:
        return []

    texts: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                text = item.get("text")
            else:
                text = item
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts


def _fallback_overall_commentary(dimension_scores: dict[str, float]) -> str:
    strongest = max(dimension_scores, key=dimension_scores.get)
    weakest = min(dimension_scores, key=dimension_scores.get)
    names = {
        "safety": "safety",
        "transit": "transit access",
        "convenience": "daily convenience",
        "parking": "parking ease",
        "environment": "environmental comfort",
    }
    return (
        f"This community stands out most for {names[strongest]}, while "
        f"{names[weakest]} looks comparatively weaker."
    )


def _fallback_dimension_comment(dimension: str, score: float) -> str:
    if dimension == "safety":
        return (
            "Safety looks like a clear strength for this neighborhood."
            if score >= 75
            else "Safety seems acceptable overall, but not the standout advantage."
            if score >= 60
            else "Safety may be one of the bigger trade-offs here."
        )
    if dimension == "transit":
        return (
            "Transit access looks relatively practical for daily commuting."
            if score >= 75
            else "Transit seems workable, though many trips may still feel car-dependent."
            if score >= 60
            else "Transit convenience appears limited compared with stronger areas."
        )
    if dimension == "convenience":
        return (
            "Daily errands and nearby amenities look like a strong point."
            if score >= 75
            else "Convenience looks decent, with some everyday needs reasonably accessible."
            if score >= 60
            else "Convenience may require more driving or planning than ideal."
        )
    if dimension == "parking":
        return (
            "Parking likely feels easier than average based on the calmer, lower-intensity signals."
            if score >= 75
            else "Parking looks manageable, though the evidence is more indirect than direct."
            if score >= 60
            else "Parking may be a trade-off, and the current evidence is somewhat limited."
        )
    return (
        "The environment looks calm and comfortable for quieter living."
        if score >= 75
        else "The environment feels reasonably balanced, though not especially quiet."
        if score >= 60
        else "Noise or activity levels may be part of the trade-off here."
    )


def _clean_sentence(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    return text
