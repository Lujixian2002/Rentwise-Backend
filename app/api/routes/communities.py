import json
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.db import crud
from app.schemas.community import (
    CommunityDetailResponse,
    CommunityMetricsResponse,
    CommunityResponse,
    ReviewKeywordConfigResponse,
    ReviewResponse,
)
from app.schemas.insight import CommunityInsightRequest, CommunityInsightResponse
from app.services.insight_service import generate_community_insight
from app.services.ingest_service import ensure_metrics_fresh, ensure_reviews_fresh
from app.services.review_keyword_config import get_review_keyword_config
from app.services.review_filter_service import filter_reviews_for_community_ui

router = APIRouter()


@router.get("", response_model=list[CommunityDetailResponse])
def list_communities(db: Session = Depends(get_db)) -> list[CommunityDetailResponse]:
    rows = crud.list_communities_with_metrics(db)
    return [_build_detail_response(community, metrics) for community, metrics in rows]


@router.get("/review-keyword-config", response_model=ReviewKeywordConfigResponse)
def get_community_review_keyword_config() -> ReviewKeywordConfigResponse:
    return get_review_keyword_config()


@router.get("/{community_id}", response_model=CommunityDetailResponse)
def get_community(community_id: str, db: Session = Depends(get_db)) -> CommunityDetailResponse:
    community = crud.get_community(db, community_id)
    if community is None:
        raise HTTPException(status_code=404, detail="Community not found")

    ensure_metrics_fresh(db, community_id)
    metrics = crud.get_metrics(db, community_id)
    return _build_detail_response(community, metrics)


@router.get("/{community_id}/reviews", response_model=list[ReviewResponse])
async def get_community_reviews(
    community_id: str,
    ai_filter: bool = Query(
        default=False,
        description="When true, remove obvious ads, spam, and off-topic comments using OpenAI when configured.",
    ),
    refresh_ai_filter: bool = Query(
        default=False,
        description="When true, recompute AI review filter decisions instead of using the cache.",
    ),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> list[ReviewResponse]:
    # Check/fetch fresh reviews if none exist
    ensure_reviews_fresh(db, community_id)
    
    reviews = crud.get_reviews_by_community(db, community_id, limit=200)
    if ai_filter:
        reviews = await filter_reviews_for_community_ui(
            reviews,
            settings,
            db,
            refresh=refresh_ai_filter,
        )

    return [
        ReviewResponse(
            post_id=r.post_id,
            platform=r.platform,
            external_id=r.external_id,
            body_text=r.body_text,
            posted_at=r.posted_at,
            author_name=r.author_name,
            like_count=r.like_count,
            parent_id=r.parent_id,
            source_url=_with_text_fragment(r.url, r.body_text),
        )
        for r in reviews
    ]


@router.post("/{community_id}/insight", response_model=CommunityInsightResponse)
async def get_community_insight(
    community_id: str,
    req: CommunityInsightRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CommunityInsightResponse:
    insight = await generate_community_insight(
        db=db,
        community_id=community_id,
        settings=settings,
        max_reviews=req.max_reviews,
        include_web_info=req.include_web_info,
    )
    if insight is None:
        raise HTTPException(status_code=404, detail="Community not found")
    return insight


def _build_detail_response(
    community,
    metrics,
) -> CommunityDetailResponse:
    community_payload = CommunityResponse(
        community_id=community.community_id,
        name=community.name,
        city=community.city,
        state=community.state,
        center_lat=community.center_lat,
        center_lng=community.center_lng,
        updated_at=community.updated_at,
    )

    metrics_payload = None
    if metrics:
        metrics_payload = CommunityMetricsResponse(
            community_id=metrics.community_id,
            median_rent=metrics.median_rent,
            rent_2b2b=metrics.rent_2b2b,
            rent_1b1b=metrics.rent_1b1b,
            avg_sqft=metrics.avg_sqft,
            grocery_density_per_km2=metrics.grocery_density_per_km2,
            crime_rate_per_100k=metrics.crime_rate_per_100k,
            rent_trend_12m_pct=metrics.rent_trend_12m_pct,
            night_activity_index=metrics.night_activity_index,
            noise_avg_db=metrics.noise_avg_db,
            noise_p90_db=metrics.noise_p90_db,
            commute_minutes=_metric_commute_minutes(metrics),
            parking_lot_density_per_km2=metrics.parking_lot_density_per_km2,
            parking_capacity_per_km2=metrics.parking_capacity_per_km2,
            poi_demand_density_per_km2=metrics.poi_demand_density_per_km2,
            overall_confidence=metrics.overall_confidence,
            updated_at=metrics.updated_at,
        )

    return CommunityDetailResponse(community=community_payload, metrics=metrics_payload)


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


def _metric_commute_minutes(metrics) -> float | None:
    if metrics.commute_minutes is not None:
        return metrics.commute_minutes

    if not metrics.details_json:
        return None
    try:
        payload = json.loads(metrics.details_json)
    except (TypeError, json.JSONDecodeError):
        return None

    value = payload.get("sources", {}).get("commute_minutes")
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
