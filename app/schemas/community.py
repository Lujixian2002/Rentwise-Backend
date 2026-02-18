from datetime import datetime

from pydantic import BaseModel


class CommunityResponse(BaseModel):
    community_id: str
    name: str
    city: str | None = None
    state: str | None = None
    center_lat: float | None = None
    center_lng: float | None = None
    updated_at: datetime | None = None


class CommunityMetricsResponse(BaseModel):
    community_id: str
    median_rent: float | None = None
    rent_2b2b: float | None = None
    rent_1b1b: float | None = None
    avg_sqft: float | None = None
    grocery_density_per_km2: float | None = None
    crime_rate_per_100k: float | None = None
    rent_trend_12m_pct: float | None = None
    night_activity_index: float | None = None
    noise_avg_db: float | None = None
    noise_p90_db: float | None = None
    overall_confidence: float | None = None
    updated_at: datetime | None = None


class CommunityDetailResponse(BaseModel):
    community: CommunityResponse
    metrics: CommunityMetricsResponse | None = None
