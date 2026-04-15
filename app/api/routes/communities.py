from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.db import crud
from app.schemas.community import (
    CommunityDetailResponse,
    CommunityMetricsResponse,
    CommunityResponse,
    ReviewResponse,
)
from app.schemas.insight import CommunityInsightRequest, CommunityInsightResponse
from app.services.insight_service import generate_community_insight
from app.services.ingest_service import ensure_metrics_fresh, ensure_reviews_fresh

router = APIRouter()


@router.get("", response_model=list[CommunityDetailResponse])
def list_communities(db: Session = Depends(get_db)) -> list[CommunityDetailResponse]:
    rows = crud.list_communities_with_metrics(db)
    return [_build_detail_response(community, metrics) for community, metrics in rows]


@router.get("/{community_id}", response_model=CommunityDetailResponse)
def get_community(community_id: str, db: Session = Depends(get_db)) -> CommunityDetailResponse:
    community = crud.get_community(db, community_id)
    if community is None:
        raise HTTPException(status_code=404, detail="Community not found")

    ensure_metrics_fresh(db, community_id)
    metrics = crud.get_metrics(db, community_id)
    return _build_detail_response(community, metrics)


@router.get("/{community_id}/reviews", response_model=list[ReviewResponse])
def get_community_reviews(
    community_id: str, db: Session = Depends(get_db)
) -> list[ReviewResponse]:
    # Check/fetch fresh reviews if none exist
    ensure_reviews_fresh(db, community_id)
    
    reviews = crud.get_reviews_by_community(db, community_id, limit=200)
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
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    insight = await generate_community_insight(
        db=db,
        community_id=community_id,
        settings=settings,
        max_reviews=req.max_reviews,
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
            overall_confidence=metrics.overall_confidence,
            updated_at=metrics.updated_at,
        )

    return CommunityDetailResponse(community=community_payload, metrics=metrics_payload)
