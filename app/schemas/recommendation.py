from pydantic import BaseModel, Field

from app.schemas.chat import PreferenceWeights


class RecommendationMetricsPreview(BaseModel):
    median_rent: float | None = None
    grocery_density_per_km2: float | None = None
    crime_rate_per_100k: float | None = None
    noise_avg_db: float | None = None
    night_activity_index: float | None = None
    commute_minutes: float | None = None


class RecommendationItem(BaseModel):
    rank: int
    community_id: str
    name: str
    city: str | None = None
    state: str | None = None
    score: float
    overall_confidence: float | None = None
    dimension_scores: PreferenceWeights
    weighted_contributions: PreferenceWeights
    metrics: RecommendationMetricsPreview


class RecommendationRequest(BaseModel):
    weights: dict[str, float] | None = None
    top_k: int = Field(default=3, ge=1, le=20)


class RecommendationResponse(BaseModel):
    weights_used: PreferenceWeights
    total_candidates: int
    scored_communities: int
    skipped_missing_metrics: int
    ranked_communities: list[RecommendationItem]
