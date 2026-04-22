import json

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import crud
from app.services.scoring_service import (
    compute_dimension_scores,
    compute_preference_scores,
    compute_weighted_preference_score,
    normalize_preference_weights,
)

_COMPARE_SYSTEM_PROMPT = """You generate concise neighborhood comparison summaries.
Ground every statement in the provided scores, metrics, and computed differences only. Do not invent facts.

Return a valid JSON object with exactly this shape:
{
  "short_summary": "...",
  "tradeoffs": {
    "community_a_strengths": ["..."],
    "community_b_strengths": ["..."]
  }
}

Rules:
1. "short_summary" should be 1-2 short sentences and mention the main tradeoff between the two communities.
2. The strengths lists must contain only labels from the allowed dimensions provided in the input.
3. Keep each strengths list to 0-4 items.
4. Prefer dimensions with clearer leads over tiny differences.
5. Use the provided community names, not the ids.
6. If one side has little evidence, keep that side's strengths list short rather than guessing."""


async def compare_communities(
    db: Session,
    community_a_id: str,
    community_b_id: str,
    community_a_name: str,
    community_b_name: str,
    settings: Settings,
    weights: dict[str, float] | None = None,
):
    weights = weights or {}
    normalized_weights = normalize_preference_weights(weights) if weights else {}

    metrics_a = crud.get_metrics(db, community_a_id)
    metrics_b = crud.get_metrics(db, community_b_id)

    if not metrics_a or not metrics_b:
        missing = []
        if not metrics_a:
            missing.append(f"missing metrics: {community_a_id}")
        if not metrics_b:
            missing.append(f"missing metrics: {community_b_id}")

        fallback_tradeoffs = {
            "community_a_strengths": [],
            "community_b_strengths": [],
        }
        row = crud.create_comparison(
            db=db,
            community_a_id=community_a_id,
            community_b_id=community_b_id,
            request_params={"weights": weights},
            weights_used=normalized_weights,
            structured_diff={},
            short_summary="Comparison incomplete due to missing metrics",
            tradeoffs=fallback_tradeoffs,
            status="missing_data",
            missing_fields=missing,
        )
        return row, {}, fallback_tradeoffs

    dict_a = {
        "median_rent": metrics_a.median_rent,
        "commute_minutes": _extract_commute_minutes(metrics_a.details_json),
        "grocery_density_per_km2": metrics_a.grocery_density_per_km2,
        "crime_rate_per_100k": metrics_a.crime_rate_per_100k,
        "rent_trend_12m_pct": metrics_a.rent_trend_12m_pct,
        "noise_avg_db": metrics_a.noise_avg_db,
        "night_activity_index": metrics_a.night_activity_index,
        "review_signal_score": None,
    }
    dict_b = {
        "median_rent": metrics_b.median_rent,
        "commute_minutes": _extract_commute_minutes(metrics_b.details_json),
        "grocery_density_per_km2": metrics_b.grocery_density_per_km2,
        "crime_rate_per_100k": metrics_b.crime_rate_per_100k,
        "rent_trend_12m_pct": metrics_b.rent_trend_12m_pct,
        "noise_avg_db": metrics_b.noise_avg_db,
        "night_activity_index": metrics_b.night_activity_index,
        "review_signal_score": None,
    }

    score_a = compute_dimension_scores(dict_a)
    score_b = compute_dimension_scores(dict_b)

    preference_score_a = compute_preference_scores(dict_a)
    preference_score_b = compute_preference_scores(dict_b)

    if normalized_weights:
        _, a_total = compute_weighted_preference_score(
            preference_score_a,
            normalized_weights,
        )
        _, b_total = compute_weighted_preference_score(
            preference_score_b,
            normalized_weights,
        )
    else:
        a_total = sum(score_a.values())
        b_total = sum(score_b.values())

    structured_diff = {}
    for dim in sorted(score_a.keys()):
        structured_diff[dim] = {
            "a": score_a[dim],
            "b": score_b[dim],
            "winner": community_a_id if score_a[dim] >= score_b[dim] else community_b_id,
            "delta": round(score_a[dim] - score_b[dim], 2),
        }

    fallback_summary, fallback_tradeoffs = _build_fallback_compare_copy(
        community_a_id=community_a_id,
        community_b_id=community_b_id,
        community_a_name=community_a_name,
        community_b_name=community_b_name,
        structured_diff=structured_diff,
        total_a=a_total,
        total_b=b_total,
    )

    generated_copy = await _generate_compare_copy(
        settings=settings,
        community_a_id=community_a_id,
        community_b_id=community_b_id,
        community_a_name=community_a_name,
        community_b_name=community_b_name,
        metrics_a=dict_a,
        metrics_b=dict_b,
        dimension_scores_a=score_a,
        dimension_scores_b=score_b,
        preference_scores_a=preference_score_a,
        preference_scores_b=preference_score_b,
        structured_diff=structured_diff,
        total_a=a_total,
        total_b=b_total,
        weights_used=normalized_weights,
    )

    short_summary = generated_copy.get("short_summary") or fallback_summary
    tradeoffs = generated_copy.get("tradeoffs") or fallback_tradeoffs

    row = crud.create_comparison(
        db=db,
        community_a_id=community_a_id,
        community_b_id=community_b_id,
        request_params={"weights": weights},
        weights_used=normalized_weights,
        structured_diff=structured_diff,
        short_summary=short_summary,
        tradeoffs=tradeoffs,
        status="ready",
    )
    return row, structured_diff, tradeoffs


async def _generate_compare_copy(
    settings: Settings,
    community_a_id: str,
    community_b_id: str,
    community_a_name: str,
    community_b_name: str,
    metrics_a: dict,
    metrics_b: dict,
    dimension_scores_a: dict[str, float],
    dimension_scores_b: dict[str, float],
    preference_scores_a: dict[str, float],
    preference_scores_b: dict[str, float],
    structured_diff: dict,
    total_a: float,
    total_b: float,
    weights_used: dict[str, float],
) -> dict:
    if not settings.openai_api_key:
        return {}

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=30.0)
    allowed_dimensions = list(structured_diff.keys())
    user_prompt = json.dumps(
        {
            "community_a": {
                "id": community_a_id,
                "name": community_a_name,
                "metrics": metrics_a,
                "dimension_scores": dimension_scores_a,
                "preference_scores": preference_scores_a,
                "overall_total": total_a,
            },
            "community_b": {
                "id": community_b_id,
                "name": community_b_name,
                "metrics": metrics_b,
                "dimension_scores": dimension_scores_b,
                "preference_scores": preference_scores_b,
                "overall_total": total_b,
            },
            "weights_used": weights_used,
            "allowed_strength_dimensions": allowed_dimensions,
            "structured_diff": structured_diff,
        },
        ensure_ascii=True,
    )

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _COMPARE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=350,
        )
        raw = completion.choices[0].message.content or ""
        data = json.loads(raw)
        tradeoffs = data.get("tradeoffs", {})
        return {
            "short_summary": _clean_sentence(data.get("short_summary")),
            "tradeoffs": {
                "community_a_strengths": _sanitize_strengths(
                    tradeoffs.get("community_a_strengths"),
                    allowed_dimensions,
                ),
                "community_b_strengths": _sanitize_strengths(
                    tradeoffs.get("community_b_strengths"),
                    allowed_dimensions,
                ),
            },
        }
    except Exception:
        return {}


def _build_fallback_compare_copy(
    community_a_id: str,
    community_b_id: str,
    community_a_name: str,
    community_b_name: str,
    structured_diff: dict,
    total_a: float,
    total_b: float,
) -> tuple[str, dict]:
    a_strengths = _top_strengths(structured_diff, community_a_id)
    b_strengths = _top_strengths(structured_diff, community_b_id)
    winner_name = community_a_name if total_a >= total_b else community_b_name

    if a_strengths and b_strengths:
        summary = (
            f"{winner_name} leads overall. "
            f"{community_a_name} stands out most for {a_strengths[0]}, while "
            f"{community_b_name} looks stronger on {b_strengths[0]}."
        )
    elif a_strengths:
        summary = (
            f"{winner_name} leads overall, with {community_a_name} strongest on "
            f"{', '.join(a_strengths[:2])}."
        )
    elif b_strengths:
        summary = (
            f"{winner_name} leads overall, with {community_b_name} strongest on "
            f"{', '.join(b_strengths[:2])}."
        )
    else:
        summary = f"{winner_name} leads overall."

    return summary, {
        "community_a_strengths": a_strengths,
        "community_b_strengths": b_strengths,
    }


def _top_strengths(
    structured_diff: dict,
    winner_id: str,
    limit: int = 4,
) -> list[str]:
    ranked = sorted(
        (
            (dimension, abs(values["delta"]))
            for dimension, values in structured_diff.items()
            if values.get("winner") == winner_id and abs(values.get("delta", 0.0)) >= 1.0
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    return [dimension for dimension, _ in ranked[:limit]]


def parse_json(text: str | None, default):
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default


def _extract_commute_minutes(details_json: str | None) -> float | None:
    payload = parse_json(details_json, {})
    value = payload.get("sources", {}).get("commute_minutes")
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_sentence(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    if not text:
        return None
    return text


def _sanitize_strengths(values, allowed_dimensions: list[str], limit: int = 4) -> list[str]:
    if not isinstance(values, list):
        return []

    allowed = {dimension.lower(): dimension for dimension in allowed_dimensions}
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        label = _clean_sentence(item)
        if not label:
            continue
        canonical = allowed.get(label.lower())
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        cleaned.append(canonical)
        if len(cleaned) >= limit:
            break
    return cleaned
