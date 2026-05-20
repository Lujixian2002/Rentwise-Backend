from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException
from openai import AsyncOpenAI

from app.db import crud
from app.schemas.agent import (
    AgentTraceStep,
    CommunityReportDimension,
    CommunityReportLocation,
    CommunityReportMetricSnapshot,
    CommunityReportResponse,
    CommunityReportReviewSource,
    CommunityReportSection,
)
from app.services.scoring_service import PREFERENCE_DIMENSIONS
from app.services.ingest_service import ensure_reviews_fresh
from app.skills.base import Skill, SkillContext

_REPORT_SYSTEM_PROMPT = """You generate personalized single-community report content for RentWise.
Use only the provided community data, metrics, dimension scores, reviews, and user preferences.

Return only a valid JSON object:
{
  "title": "...",
  "summary": "...",
  "sections": [
    {"type": "overview|fit|dimensions|risk_alerts|viewing_checklist|sources", "title": "...", "content": "...", "items": ["..."]}
  ]
}

Rules:
1. Do not invent facts or exact values not present in the input.
2. Keep the report renter-focused and specific to this community.
3. Generate structured report content only; do not generate HTML.
4. Include risk alerts for low-confidence or missing fields.
5. Include a practical viewing checklist."""

_REPORT_SECTION_TYPES = {
    "overview",
    "fit",
    "dimensions",
    "risk_alerts",
    "viewing_checklist",
    "sources",
}


class CommunityReportSkill(Skill):
    name = "community_report"
    description = (
        "Generate a personalized single-community report with structured sections "
        "and an embeddable HTML fragment."
    )

    async def run(
        self,
        payload: dict[str, Any],
        context: SkillContext,
    ) -> CommunityReportResponse:
        community_id = str(payload.get("community_id") or "").strip()
        if not community_id:
            raise HTTPException(status_code=422, detail="community_id is required")

        community = crud.get_community(context.db, community_id)
        if community is None:
            raise HTTPException(status_code=404, detail="Community not found")

        metrics = crud.get_metrics(context.db, community_id)
        dimension_scores = crud.get_dimension_scores(context.db, community_id)
        ensure_reviews_fresh(context.db, community_id)
        reviews = crud.get_reviews_by_community(context.db, community_id, limit=8)
        preferences = _clean_preferences(payload.get("user_preferences"))

        trace = [
            AgentTraceStep(
                step="report_data_load",
                status="success",
                message="Loaded community data for report generation.",
                detail={
                    "community_id": community_id,
                    "has_metrics": metrics is not None,
                    "dimension_count": len(dimension_scores),
                    "review_count": len(reviews),
                },
            )
        ]

        generated = await _generate_report_with_llm(
            context=context,
            community=community,
            metrics=metrics,
            dimension_scores=dimension_scores,
            reviews=reviews,
            preferences=preferences,
        )
        trace.append(
            AgentTraceStep(
                step="report_generation",
                status="success" if generated else "skipped",
                message=(
                    "Generated personalized report content with LLM."
                    if generated
                    else "Used deterministic fallback report content."
                ),
                detail={"llm_enabled": bool(context.settings.openai_api_key)},
            )
        )

        if generated is None:
            generated = _fallback_report(
                community=community,
                metrics=metrics,
                dimension_scores=dimension_scores,
                preferences=preferences,
            )

        sections = _sanitize_sections(generated.get("sections"))
        if not sections:
            sections = _fallback_sections(
                community=community,
                metrics=metrics,
                dimension_scores=dimension_scores,
                preferences=preferences,
            )

        title = _clean_text(generated.get("title")) or community.name
        summary = _clean_text(generated.get("summary")) or _default_summary(
            community.name
        )
        review_sources = _report_reviews(reviews)
        html_fragment = _sanitize_html_fragment(generated.get("html_fragment"))
        if not html_fragment:
            html_fragment = _render_html_fragment(
                title,
                summary,
                sections,
                review_sources=review_sources,
            )

        trace.append(
            AgentTraceStep(
                step="report_finalize",
                status="success",
                message="Finalized structured report sections and HTML fragment.",
                detail={"section_count": len(sections)},
            )
        )

        return CommunityReportResponse(
            community_id=community_id,
            title=title,
            summary=summary,
            location=_location_payload(community),
            metrics=CommunityReportMetricSnapshot(**_metrics_payload(metrics)),
            dimensions=_report_dimensions(dimension_scores),
            reviews=review_sources,
            user_preferences=preferences,
            sections=sections,
            html_fragment=html_fragment,
            agent_trace=trace,
        )


async def _generate_report_with_llm(
    context: SkillContext,
    community,
    metrics,
    dimension_scores,
    reviews,
    preferences: dict[str, float],
) -> dict | None:
    if not context.settings.openai_api_key:
        return None

    client = AsyncOpenAI(api_key=context.settings.openai_api_key, timeout=30.0)
    prompt = json.dumps(
        {
            "community": _community_payload(community),
            "metrics": _metrics_payload(metrics),
            "dimension_scores": _dimension_payload(dimension_scores),
            "reviews": [
                {
                    "platform": review.platform,
                    "author_name": review.author_name,
                    "body_text": _trim(review.body_text, limit=260),
                    "source_url": _review_source_url(review),
                }
                for review in reviews
                if review.body_text
            ],
            "user_preferences": preferences,
        },
        ensure_ascii=True,
    )

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.35,
            max_tokens=1400,
        )
        raw = completion.choices[0].message.content or ""
        return json.loads(raw)
    except Exception:
        return None


def _fallback_report(
    community,
    metrics,
    dimension_scores,
    preferences: dict[str, float],
) -> dict:
    title = community.name
    summary = _default_summary(community.name)
    sections = _fallback_sections(community, metrics, dimension_scores, preferences)
    return {
        "title": title,
        "summary": summary,
        "sections": [section.model_dump() for section in sections],
    }


def _fallback_sections(
    community,
    metrics,
    dimension_scores,
    preferences: dict[str, float],
) -> list[CommunityReportSection]:
    dimensions = _dimension_payload(dimension_scores)
    missing = [
        dimension
        for dimension in PREFERENCE_DIMENSIONS
        if not any(item["dimension"] == dimension for item in dimensions)
    ]
    fit_items = []
    for dimension, weight in sorted(
        preferences.items(), key=lambda item: item[1], reverse=True
    )[:3]:
        score = next(
            (item["score_0_100"] for item in dimensions if item["dimension"] == dimension),
            None,
        )
        fit_items.append(
            f"{dimension}: preference weight {weight:g}"
            + (f", score {score:g}" if score is not None else ", score unavailable")
        )

    return [
        CommunityReportSection(
            type="overview",
            title="Overview",
            content=_default_summary(community.name),
        ),
        CommunityReportSection(
            type="fit",
            title="Fit For You",
            items=fit_items or ["No user preference weights were provided."],
        ),
        CommunityReportSection(
            type="dimensions",
            title="Five Dimensions",
            items=[
                f"{item['dimension']}: {item['score_0_100'] if item['score_0_100'] is not None else 'N/A'} - {item['summary']}"
                for item in dimensions
            ],
        ),
        CommunityReportSection(
            type="risk_alerts",
            title="Risk Alerts",
            items=(
                [f"Missing or low-confidence data for: {', '.join(missing)}."]
                if missing
                else ["No missing dimension scores were detected in the current data."]
            ),
        ),
        CommunityReportSection(
            type="viewing_checklist",
            title="Viewing Checklist",
            items=[
                "Visit at commute time and compare travel time with your routine.",
                "Check parking availability during evening hours.",
                "Listen for road noise inside the unit with windows closed and open.",
            ],
        ),
        CommunityReportSection(
            type="sources",
            title="Sources And Confidence",
            items=[
                f"Overall metrics confidence: {getattr(metrics, 'overall_confidence', None) if metrics else 'unavailable'}",
                "Scores are generated from RentWise structured metrics when available.",
            ],
        ),
    ]


def _sanitize_sections(payload) -> list[CommunityReportSection]:
    if not isinstance(payload, list):
        return []
    sections = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        section_type = str(item.get("type") or "").strip()
        if section_type not in _REPORT_SECTION_TYPES:
            continue
        sections.append(
            CommunityReportSection(
                type=section_type,
                title=_clean_text(item.get("title")) or section_type.replace("_", " ").title(),
                content=_clean_text(item.get("content")),
                items=_clean_string_list(item.get("items")),
            )
        )
    return sections


def _sanitize_html_fragment(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    html_fragment = value.strip()
    forbidden = re.compile(
        r"<\s*(script|style|iframe|object|embed|form)\b|on\w+\s*=",
        re.IGNORECASE,
    )
    if forbidden.search(html_fragment):
        return ""
    return html_fragment


def _render_html_fragment(
    title: str,
    summary: str,
    sections: list[CommunityReportSection],
    review_sources: list[CommunityReportReviewSource] | None = None,
) -> str:
    parts = [
        '<section class="community-report">',
        f"<header><h1>{html.escape(title)}</h1><p>{html.escape(summary)}</p></header>",
    ]
    for section in sections:
        parts.append(f'<section data-section="{html.escape(section.type)}">')
        parts.append(f"<h2>{html.escape(section.title)}</h2>")
        if section.content:
            parts.append(f"<p>{html.escape(section.content)}</p>")
        if section.items:
            parts.append("<ul>")
            for item in section.items:
                parts.append(f"<li>{html.escape(item)}</li>")
            parts.append("</ul>")
        parts.append("</section>")
    linked_reviews = [review for review in review_sources or [] if review.source_url]
    if linked_reviews:
        parts.append('<section data-section="review_sources">')
        parts.append("<h2>Review Sources</h2>")
        parts.append("<ul>")
        for index, review in enumerate(linked_reviews, start=1):
            label_parts = [f"Comment {index}"]
            if review.platform:
                label_parts.append(review.platform.title())
            if review.author_name:
                label_parts.append(review.author_name)
            label = " - ".join(label_parts)
            parts.append(
                f'<li><a href="{html.escape(review.source_url, quote=True)}" '
                f'target="_blank" rel="noopener noreferrer">{html.escape(label)}</a></li>'
            )
        parts.append("</ul>")
        parts.append("</section>")
    parts.append("</section>")
    return "".join(parts)


def _community_payload(community) -> dict:
    return {
        "community_id": community.community_id,
        "name": community.name,
        "city": community.city,
        "state": community.state,
        "center_lat": community.center_lat,
        "center_lng": community.center_lng,
    }


def _location_payload(community) -> CommunityReportLocation:
    return CommunityReportLocation(
        name=community.name,
        city=community.city,
        state=community.state,
        center_lat=community.center_lat,
        center_lng=community.center_lng,
    )


def _metrics_payload(metrics) -> dict:
    if metrics is None:
        return {}
    core_metric_values = [
        metrics.median_rent,
        metrics.grocery_density_per_km2,
        metrics.crime_rate_per_100k,
        metrics.rent_trend_12m_pct,
        metrics.night_activity_index,
        metrics.noise_avg_db,
    ]
    available_core_metrics = sum(value is not None for value in core_metric_values)
    return {
        "median_rent": metrics.median_rent,
        "commute_minutes": metrics.commute_minutes,
        "grocery_density_per_km2": metrics.grocery_density_per_km2,
        "crime_rate_per_100k": metrics.crime_rate_per_100k,
        "rent_trend_12m_pct": metrics.rent_trend_12m_pct,
        "noise_avg_db": metrics.noise_avg_db,
        "night_activity_index": metrics.night_activity_index,
        "parking_lot_density_per_km2": metrics.parking_lot_density_per_km2,
        "parking_capacity_per_km2": metrics.parking_capacity_per_km2,
        "poi_demand_density_per_km2": metrics.poi_demand_density_per_km2,
        "overall_confidence": round(available_core_metrics / len(core_metric_values), 2),
    }


def _dimension_payload(dimension_scores) -> list[dict]:
    return [
        {
            "dimension": score.dimension,
            "score_0_100": score.score_0_100,
            "summary": score.summary,
            "data_origin": score.data_origin,
        }
        for score in dimension_scores
        if score.dimension
    ]


def _report_dimensions(dimension_scores) -> list[CommunityReportDimension]:
    dimensions = []
    for score in dimension_scores:
        if score.dimension not in PREFERENCE_DIMENSIONS:
            continue
        dimensions.append(
            CommunityReportDimension(
                dimension=score.dimension,
                score_0_100=score.score_0_100,
                summary=score.summary,
                data_origin=score.data_origin,
            )
        )
    return dimensions


def _report_reviews(reviews) -> list[CommunityReportReviewSource]:
    payload = []
    for review in reviews:
        if not review.body_text:
            continue
        body_text = _trim(review.body_text, limit=320)
        payload.append(
            CommunityReportReviewSource(
                platform=review.platform,
                author_name=review.author_name,
                body_text=body_text,
                posted_at=review.posted_at.isoformat() if review.posted_at else None,
                source_url=_review_source_url(review, body_text),
            )
        )
    return payload


def _review_source_url(review, display_text: str | None = None) -> str | None:
    url = None
    if review.url:
        url = review.url
    elif review.platform == "youtube":
        video_id = _extract_youtube_video_id(review.external_id, review.parent_id)
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"
            if review.external_id:
                url = f"{url}&lc={review.external_id}"
    return _with_text_fragment(url, display_text if display_text is not None else review.body_text)


def _with_text_fragment(url: str | None, text: str | None) -> str | None:
    if not url:
        return None
    fragment_text = _text_fragment_phrase(text)
    if not fragment_text:
        return url
    return f"{url}#:~:text={quote(fragment_text, safe='')}"


def _text_fragment_phrase(text: str | None) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9\s.,!?'\-]", " ", text or "")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


def _extract_youtube_video_id(*values) -> str | None:
    for value in values:
        if not isinstance(value, str):
            continue
        if value.startswith("yt-"):
            continue
        if len(value) == 11 and re.match(r"^[A-Za-z0-9_-]+$", value):
            return value
    return None


def _clean_preferences(value) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    preferences = {}
    for key, raw in value.items():
        dimension = str(key).strip().lower()
        if dimension not in PREFERENCE_DIMENSIONS:
            continue
        try:
            preferences[dimension] = float(raw)
        except (TypeError, ValueError):
            continue
    return preferences


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _clean_string_list(value, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = _clean_text(item)
        if text:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def _trim(value: str, limit: int) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _default_summary(name: str) -> str:
    return f"{name} is summarized using the current RentWise community data."
