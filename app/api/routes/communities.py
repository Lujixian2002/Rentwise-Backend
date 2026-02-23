from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import crud
from app.schemas.community import (
    CommunityDetailResponse,
    CommunityMetricsResponse,
    CommunityResponse,
    ReviewResponse,
)
from app.services.ingest_service import ensure_metrics_fresh, ensure_reviews_fresh

router = APIRouter()


@router.get("/{community_id}", response_model=CommunityDetailResponse)
def get_community(community_id: str, db: Session = Depends(get_db)) -> CommunityDetailResponse:
    community = crud.get_community(db, community_id)
    if community is None:
        raise HTTPException(status_code=404, detail="Community not found")

    ensure_metrics_fresh(db, community_id)
    metrics = crud.get_metrics(db, community_id)

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


@router.get("/{community_id}/reviews", response_model=list[ReviewResponse])
def get_community_reviews(
    community_id: str, db: Session = Depends(get_db)
) -> list[ReviewResponse]:
    # Check/fetch fresh reviews if none exist
    ensure_reviews_fresh(db, community_id)
    
    reviews = crud.get_reviews_by_community(db, community_id, limit=50)
    return [
        ReviewResponse(
            post_id=r.post_id,
            platform=r.platform,
            body_text=r.body_text,
            posted_at=r.posted_at,
        )
        for r in reviews
    ]
