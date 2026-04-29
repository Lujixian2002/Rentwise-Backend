from __future__ import annotations

import json
from urllib.parse import urlparse

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db import crud
from app.schemas.insight import (
    CommunityInsightResponse,
    CommunityWebInfo,
    CommunityWebSource,
    DimensionCommentary,
)
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

_COMMUNITY_WEB_INFO_SYSTEM_PROMPT = """You generate concise neighborhood background cards.
Use web search to gather basic public information about the named neighborhood or community.

Return a valid JSON object with exactly this shape:
{
  "summary": "...",
  "highlights": ["...", "...", "..."]
}

Rules:
1. Search the web before answering.
2. Focus on stable, renter-useful basics such as neighborhood character, major nearby destinations, parks, shopping areas, schools, development pattern, and where the area sits inside the city.
3. Avoid exact home prices, market forecasts, rankings, rumors, and promotional language.
4. If the place name is ambiguous, use the provided city and state to disambiguate it.
5. "summary" should be 1-2 short sentences.
6. "highlights" should contain 2-4 short sentences.
7. If evidence is weak, say that briefly instead of overstating."""

_COMMUNITY_WEB_INFO_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "highlights": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "highlights"],
    "additionalProperties": False,
}


async def generate_community_insight(
    db: Session,
    community_id: str,
    settings: Settings,
    max_reviews: int = 20,
    include_web_info: bool = True,
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

    community_web_info = None
    if include_web_info:
        community_web_info = await _generate_community_web_info(
            settings=settings,
            community_name=community.name,
            city=community.city,
            state=community.state,
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
        community_web_info=community_web_info,
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
    if not settings.openai_api_key:
        return {
            "overall_commentary": _fallback_overall_commentary(dimension_scores),
            "dimensions": {
                dimension: _fallback_dimension_comment(dimension, score)
                for dimension, score in dimension_scores.items()
            },
        }

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


async def _generate_community_web_info(
    settings: Settings,
    community_name: str,
    city: str | None,
    state: str | None,
) -> CommunityWebInfo | None:
    if not settings.openai_api_key:
        return None

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_web_search_timeout_sec,
    )
    if not hasattr(client, "responses"):
        return None

    search_tool = {"type": "web_search"}
    user_location = _build_user_location(city, state)
    if user_location:
        search_tool["user_location"] = user_location

    user_prompt = json.dumps(
        {
            "community": {
                "name": community_name,
                "city": city,
                "state": state,
            },
            "task": "Search the web and summarize stable background information for this community.",
        },
        ensure_ascii=True,
    )

    try:
        response = await client.responses.create(
            model=settings.openai_web_search_model,
            input=[
                {"role": "system", "content": _COMMUNITY_WEB_INFO_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            tools=[search_tool],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "community_web_info",
                    "strict": True,
                    "schema": _COMMUNITY_WEB_INFO_SCHEMA,
                }
            },
            max_output_tokens=500,
        )
        raw = _extract_response_text(response)
        data = json.loads(raw)
    except Exception:
        return None

    summary = _clean_sentence(data.get("summary"))
    highlights = _clean_string_list(data.get("highlights"), limit=4)
    if not summary:
        return None

    sources = _extract_web_sources(response)
    if not sources:
        return None

    return CommunityWebInfo(
        summary=summary,
        highlights=highlights,
        sources=sources,
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


def _extract_response_text(response) -> str:
    output_text = _obj_get(response, "output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "message":
            continue
        for content_item in _obj_get(output_item, "content", []) or []:
            text = _obj_get(content_item, "text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _extract_web_sources(response, limit: int = 6) -> list[CommunityWebSource]:
    titles_by_url = _extract_citation_titles(response)
    seen: set[str] = set()
    sources: list[CommunityWebSource] = []

    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "web_search_call":
            continue
        action = _obj_get(output_item, "action", {})
        for source in _obj_get(action, "sources", []) or []:
            url = _obj_get(source, "url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                CommunityWebSource(
                    url=url,
                    domain=_extract_domain(url),
                    title=titles_by_url.get(url),
                )
            )
            if len(sources) >= limit:
                return sources
    return sources


def _extract_citation_titles(response) -> dict[str, str]:
    titles: dict[str, str] = {}

    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "message":
            continue
        for content_item in _obj_get(output_item, "content", []) or []:
            for annotation in _obj_get(content_item, "annotations", []) or []:
                ann_type = _obj_get(annotation, "type")
                if ann_type == "url_citation":
                    url = _obj_get(annotation, "url")
                    title = _obj_get(annotation, "title")
                else:
                    citation = _obj_get(annotation, "url_citation", {})
                    url = _obj_get(citation, "url")
                    title = _obj_get(citation, "title")
                if isinstance(url, str) and url and isinstance(title, str) and title.strip():
                    titles[url] = title.strip()

    return titles


def _build_user_location(city: str | None, state: str | None) -> dict | None:
    if not city and not state:
        return None

    payload = {"type": "approximate", "country": "US"}
    if city:
        payload["city"] = city
    if state:
        payload["region"] = state
    return payload


def _extract_domain(url: str) -> str | None:
    netloc = urlparse(url).netloc.strip().lower()
    return netloc or None


def _obj_get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


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


def _clean_string_list(value, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []

    cleaned: list[str] = []
    for item in value:
        text = _clean_sentence(item)
        if not text:
            continue
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned
